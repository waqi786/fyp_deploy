"""The Spark engine must produce exactly the same catalog as the local engine (same rules, same merge)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime

import pytest

from resora_pipeline import analytics as A
from resora_pipeline.orchestrator import Pipeline

from conftest import write_corpus

pyspark = pytest.importorskip("pyspark")
pytestmark = [pytest.mark.spark, pytest.mark.skipif(shutil.which("java") is None, reason="needs a Java runtime")]


def test_spark_etl_matches_local_engine(config, lake, corpus, tmp_path):
    write_corpus(lake, corpus)
    local = Pipeline(config, lake=lake)
    local_papers, _ = local.etl_local(run_id="local")

    from dataclasses import replace

    spark_config = replace(config, catalog_database_url=f"sqlite:///{tmp_path / 'spark.sqlite3'}")
    spark_pipeline = Pipeline(spark_config, lake=lake)
    from resora_pipeline.spark.etl_job import get_spark, run_spark_etl

    stats = run_spark_etl(spark_config, lake, spark_pipeline.db, run_id="spark", master="local[2]")
    assert stats["unique_papers"] == len(corpus) == len(local_papers)
    spark_papers = spark_pipeline.db.papers()
    assert {p["paper_id"]: sorted(p["source_records"]) for p in spark_papers} == {p["paper_id"]: sorted(p["source_records"]) for p in local_papers}
    assert lake.storage.list("curated/papers_parquet/run=spark")  # Parquet written to the lake

    from resora_pipeline.spark.analytics_job import run_spark_analytics

    spark = get_spark(master="local[2]")
    frame = spark.read.parquet(str(lake.storage.root / "curated/papers_parquet/run=spark"))
    year = datetime.now(UTC).year
    spark_out = run_spark_analytics(spark, frame, current_year=year)
    local_out = A.run_all(local_papers, current_year=year)
    assert spark_out["paper_count"] == local_out["paper_count"]
    assert spark_out["publication_trends"] == local_out["publication_trends"]
    assert [t["topic"] for t in spark_out["topic_trends"]] == [t["topic"] for t in local_out["topic_trends"]]
    assert spark_out["source_coverage"]["papers_per_source"] == local_out["source_coverage"]["papers_per_source"]
    assert [g["topics"] for g in spark_out["gap_candidates"]] == [sorted(g["topics"]) for g in local_out["gap_candidates"]]
