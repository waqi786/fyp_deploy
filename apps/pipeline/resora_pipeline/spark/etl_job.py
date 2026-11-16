"""PySpark ETL: read the raw zone, normalize, deduplicate at scale and load the curated catalog.

    spark-submit --py-files resora_pipeline.zip -m resora_pipeline.cli run --engine spark ...

Scalable deduplication:
  1. Normalize every envelope in parallel (mapPartitions) with the same functions as the local engine.
  2. Keep the latest fetch of each source record (reduceByKey on record_id).
  3. Identifier edges: records sharing a DOI or arXiv id (groupByKey → star edges, O(n)).
  4. Title edges: Spark ML MinHashLSH on character-trigram sets (HashingTF, binary) with approxSimilarityJoin at
     Jaccard distance ≤ 0.5 produces candidate pairs; each pair is verified with `match_rule` (years, authors,
     conflicting DOIs) — exactly the rules of the local engine.
  5. Connected components by iterative minimum-label propagation (DataFrames), so transitive matches
     (arXiv ↔ OpenAlex ↔ Crossref) end up in one cluster.
  6. Merge each cluster with `merge`, write Parquet to the lake (partitioned by year) and upsert into the catalog DB.
"""

from __future__ import annotations

import json
import time
from typing import Any

from resora_pipeline.catalog_db import CatalogDB
from resora_pipeline.config import PipelineConfig
from resora_pipeline.dedup import match_rule, merge
from resora_pipeline.lake import DataLake, LocalStorage
from resora_pipeline.normalize import normalize_envelope
from resora_pipeline.text import char_shingles

MAX_ITERATIONS = 30


def get_spark(app_name: str = "resora-etl", master: str | None = None):  # noqa: ANN201
    from pyspark.sql import SparkSession

    builder = SparkSession.builder.appName(app_name).config("spark.sql.session.timeZone", "UTC").config("spark.ui.showConsoleProgress", "false")
    builder = builder.config("spark.driver.extraJavaOptions", "-Djava.security.manager=allow").config("spark.sql.shuffle.partitions", "8")
    if master:
        builder = builder.master(master)
    return builder.getOrCreate()


def _paths(lake: DataLake, config: PipelineConfig) -> list[str]:
    files = lake.raw_files()
    storage = lake.storage
    if isinstance(storage, LocalStorage):
        return [str(storage.root / key) for key in files]
    bucket_prefix = config.lake_uri.replace("s3://", "s3a://").rstrip("/")
    return [f"{bucket_prefix}/{key}" for key in files]


def _identifier_keys(record: dict[str, Any]) -> list[str]:
    keys = []
    if record.get("doi"):
        keys.append(f"doi:{record['doi']}")
    if record.get("arxiv_id"):
        keys.append(f"arxiv:{record['arxiv_id']}")
    return keys


def _star(members: list[int]) -> list[tuple[int, int]]:
    ordered = sorted(set(members))
    return [(ordered[0], other) for other in ordered[1:]]


def connected_components(spark, vertices_rdd, edges_rdd):  # noqa: ANN001, ANN201
    """Minimum-label propagation over an undirected graph. Returns a DataFrame (idx, comp)."""
    from pyspark.sql import functions as F

    labels = spark.createDataFrame(vertices_rdd.map(lambda idx: (idx, idx)), "idx long, comp long")
    edges = spark.createDataFrame(edges_rdd.flatMap(lambda e: [(e[0], e[1]), (e[1], e[0])]), "src long, dst long").distinct().cache()
    if edges.rdd.isEmpty():
        return labels
    for _ in range(MAX_ITERATIONS):
        messages = edges.join(labels, edges.src == labels.idx).select(F.col("dst").alias("idx"), F.col("comp"))
        updated = labels.unionByName(messages).groupBy("idx").agg(F.min("comp").alias("comp")).cache()
        changed = updated.join(labels.withColumnRenamed("comp", "old"), "idx").filter(F.col("comp") != F.col("old")).count()
        labels = updated
        if changed == 0:
            break
    return labels


def run_spark_etl(config: PipelineConfig, lake: DataLake, db: CatalogDB, *, run_id: str, master: str | None = None) -> dict[str, Any]:
    from pyspark.ml.feature import HashingTF, MinHashLSH
    from pyspark.sql import functions as F

    started = time.perf_counter()
    spark = get_spark(master=master or "local[*]")
    sc = spark.sparkContext
    paths = _paths(lake, config)
    if not paths:
        return {"run_id": run_id, "raw_records": 0, "unique_papers": 0, "duplicates_merged": 0, "engine": "spark"}

    raw = sc.textFile(",".join(paths)).filter(lambda line: line.strip())
    raw_count = raw.count()
    normalized = raw.map(json.loads).map(normalize_envelope).filter(lambda record: record is not None)
    latest = normalized.map(lambda r: (r["record_id"], r)).reduceByKey(lambda a, b: a if str(a.get("fetched_at") or "") >= str(b.get("fetched_at") or "") else b).values()
    indexed = latest.zipWithIndex().map(lambda pair: (pair[1], pair[0])).cache()
    record_count = indexed.count()

    # 3. identifier edges
    id_edges = indexed.flatMap(lambda t: [(key, t[0]) for key in _identifier_keys(t[1])]).groupByKey().flatMap(lambda kv: _star(list(kv[1])))

    # 4. MinHash LSH title candidates, verified with the same rules as the local engine
    shingles = spark.createDataFrame(
        indexed.map(lambda t: (t[0], sorted(char_shingles(t[1].get("title_norm") or "")))).filter(lambda t: len(t[1]) >= 6),
        "idx long, shingles array<string>",
    )
    title_edges = sc.emptyRDD()
    if shingles.limit(2).count() > 1:
        features = HashingTF(inputCol="shingles", outputCol="features", numFeatures=1 << 18, binary=True).transform(shingles)
        model = MinHashLSH(inputCol="features", outputCol="hashes", numHashTables=8, seed=1729).fit(features)
        pairs = (
            model.approxSimilarityJoin(features, features, 0.5, distCol="distance")
            .select(F.col("datasetA.idx").alias("a"), F.col("datasetB.idx").alias("b"))
            .filter(F.col("a") < F.col("b"))
        )
        records_by_idx = indexed
        candidate = pairs.rdd.map(lambda row: (row["a"], row["b"]))
        joined = candidate.join(records_by_idx).map(lambda kv: (kv[1][0], (kv[0], kv[1][1]))).join(records_by_idx)
        title_edges = joined.filter(lambda kv: match_rule(kv[1][0][1], kv[1][1]) is not None).map(lambda kv: (kv[1][0][0], kv[0]))
    candidate_count = title_edges.count() if title_edges is not None else 0

    # 5. connected components
    edges = id_edges.union(title_edges).cache()
    components = connected_components(spark, indexed.keys(), edges)
    comp_rdd = components.rdd.map(lambda row: (row["idx"], row["comp"]))

    # 6. merge + load
    papers = indexed.join(comp_rdd).map(lambda kv: (kv[1][1], kv[1][0])).groupByKey().map(lambda kv: merge(list(kv[1]))).cache()
    paper_count = papers.count()
    papers_json = papers.map(lambda paper: json.dumps(paper, ensure_ascii=False))
    storage = lake.storage
    if isinstance(storage, LocalStorage):
        parquet_path = str(storage.root / f"curated/papers_parquet/run={run_id}")
        spark.read.json(papers_json).write.mode("overwrite").partitionBy("year").parquet(parquet_path)
    written = 0
    batch: list[dict[str, Any]] = []
    for paper in papers.toLocalIterator():
        batch.append(paper)
        if len(batch) >= 2000:
            written += db.upsert_papers(batch, run_id=run_id)
            batch.clear()
    written += db.upsert_papers(batch, run_id=run_id)
    lake.write_jsonl(f"curated/papers/run={run_id}/papers.jsonl.gz", papers.collect() if paper_count <= 200_000 else [])
    return {
        "run_id": run_id, "engine": "spark", "raw_records": raw_count, "normalized": record_count,
        "input_records": record_count, "unique_papers": paper_count, "duplicates_merged": record_count - paper_count,
        "duplicate_rate": round((record_count - paper_count) / record_count, 4) if record_count else 0.0,
        "verified_title_edges": candidate_count, "papers_written": written, "seconds": round(time.perf_counter() - started, 3),
    }
