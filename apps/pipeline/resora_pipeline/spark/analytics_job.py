"""Spark SQL analytics over the curated catalog (same outputs as resora_pipeline.analytics, for big datasets).

    papers = spark.read.parquet("<lake>/curated/papers_parquet/run=<id>")   # or a DataFrame built from the catalog
    result = run_spark_analytics(spark, papers, current_year=2026)
"""

from __future__ import annotations

from typing import Any


def run_spark_analytics(spark, papers, *, current_year: int, window: int = 2, min_recent: int = 3, min_topic: int = 5) -> dict[str, Any]:  # noqa: ANN001
    papers.createOrReplaceTempView("papers")
    spark.sql("SELECT paper_id, year, citation_count, explode(array_distinct(topics)) AS topic FROM papers WHERE topics IS NOT NULL").createOrReplaceTempView("paper_topics")

    trends = spark.sql(
        """SELECT year, COUNT(*) AS papers, SUM(COALESCE(citation_count,0)) AS citations,
                  SUM(CASE WHEN is_open_access THEN 1 ELSE 0 END) AS open_access
           FROM papers WHERE year IS NOT NULL GROUP BY year ORDER BY year"""
    ).collect()

    topic_rows = spark.sql(
        """SELECT topic, year, COUNT(*) AS n FROM paper_topics GROUP BY topic, year"""
    ).collect()
    totals: dict[str, int] = {}
    by_year: dict[str, dict[str, int]] = {}
    for row in topic_rows:
        totals[row["topic"]] = totals.get(row["topic"], 0) + row["n"]
        if row["year"] is not None:
            by_year.setdefault(row["topic"], {})[str(row["year"])] = row["n"]
    top_topics = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:15]

    last = current_year - 1
    recent_lo, prior_lo, prior_hi = last - window + 1, last - 2 * window + 1, last - window
    hot = spark.sql(
        f"""SELECT topic,
                   SUM(CASE WHEN year BETWEEN {recent_lo} AND {last} THEN 1 ELSE 0 END) AS recent,
                   SUM(CASE WHEN year BETWEEN {prior_lo} AND {prior_hi} THEN 1 ELSE 0 END) AS prior
            FROM paper_topics GROUP BY topic"""
    ).collect()
    hot_rows = []
    for row in hot:
        if row["recent"] < min_recent:
            continue
        growth = (row["recent"] + 1) / (row["prior"] + 1)
        status = "emerging" if row["prior"] <= 1 else ("growing" if growth >= 1.5 else "steady")
        if status != "steady":
            hot_rows.append({"topic": row["topic"], "status": status, "recent": row["recent"], "prior": row["prior"], "growth": round(growth, 2), "recent_years": [recent_lo, last], "prior_years": [prior_lo, prior_hi]})
    hot_rows.sort(key=lambda r: (-r["growth"], -r["recent"], r["topic"]))

    citations = spark.sql(
        """SELECT year, percentile_approx(citation_count, 0.5) AS median, percentile_approx(citation_count, 0.9) AS p90,
                  MAX(citation_count) AS max, COUNT(*) AS papers
           FROM papers WHERE year IS NOT NULL GROUP BY year ORDER BY year"""
    ).collect()

    coverage = spark.sql("SELECT source, COUNT(*) AS n FROM (SELECT explode(sources) AS source FROM papers) GROUP BY source").collect()
    unique_to = spark.sql("SELECT sources[0] AS source, COUNT(*) AS n FROM papers WHERE size(sources) = 1 GROUP BY sources[0]").collect()
    total = papers.count()

    gap_rows = []
    if total >= 10:
        pairs = spark.sql(

            f"""WITH f AS (SELECT topic, COUNT(*) AS n FROM paper_topics GROUP BY topic HAVING COUNT(*) >= {min_topic}),
                    co AS (SELECT x.topic AS a, y.topic AS b, COUNT(*) AS together FROM paper_topics x JOIN paper_topics y
                           ON x.paper_id = y.paper_id AND x.topic < y.topic GROUP BY x.topic, y.topic)
               SELECT fa.topic AS a, fb.topic AS b, fa.n AS na, fb.n AS nb, COALESCE(co.together, 0) AS together
               FROM f fa JOIN f fb ON fa.topic < fb.topic LEFT JOIN co ON co.a = fa.topic AND co.b = fb.topic"""
        )
        for row in pairs.collect():
            a, b = row["a"], row["b"]
            if a.lower() in b.lower() or b.lower() in a.lower():
                continue
            expected = row["na"] * row["nb"] / total
            if expected < 2:
                continue
            lift = row["together"] / expected
            if lift <= 0.35:
                gap_rows.append({"topics": [a, b], "papers_a": row["na"], "papers_b": row["nb"], "together": row["together"], "expected": round(expected, 2), "lift": round(lift, 3), "level": "strong" if expected >= 8 and row["together"] == 0 else ("moderate" if expected >= 4 else "limited")})
        gap_rows.sort(key=lambda r: (r["lift"], -r["expected"]))

    return {
        "paper_count": total,
        "publication_trends": [{"year": r["year"], "papers": r["papers"], "citations": r["citations"], "open_access": r["open_access"]} for r in trends],
        "topic_trends": [{"topic": topic, "total": count, "by_year": dict(sorted(by_year.get(topic, {}).items()))} for topic, count in top_topics],
        "hot_topics": hot_rows[:15],
        "citation_patterns": {"by_year": [{"year": r["year"], "median": r["median"], "p90": float(r["p90"]), "max": r["max"], "papers": r["papers"]} for r in citations]},
        "source_coverage": {"papers_per_source": {r["source"]: r["n"] for r in coverage}, "unique_to_source": {r["source"]: r["n"] for r in unique_to}},
        "gap_candidates": gap_rows[:15],
    }
