"""Apache Airflow DAG: daily incremental ingestion → Spark ETL → analytics → search index.

Copy to $AIRFLOW_HOME/dags (docker-compose.bigdata.yml mounts this folder). Topics come from the Airflow Variable
`resora_topics` (JSON list); credentials come from the environment, never from the DAG.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

DEFAULT_TOPICS = ["large language models", "computer vision", "machine learning in healthcare"]
SOURCES = ["openalex", "arxiv", "crossref", "semantic_scholar"]


def _pipeline():
    from resora_pipeline.orchestrator import Pipeline

    return Pipeline()


def ingest(**context):
    topics = json.loads(Variable.get("resora_topics", default_var=json.dumps(DEFAULT_TOPICS)))
    run_id = context["run_id"].replace(":", "").replace("+", "")[:40]
    result = _pipeline().ingest(topics, sources=SOURCES, run_id=run_id, max_records=int(Variable.get("resora_max_records", default_var="500")))
    context["ti"].xcom_push(key="run_id", value=run_id)
    return result["records"]


def etl(**context):
    from resora_pipeline.spark.etl_job import run_spark_etl

    pipeline = _pipeline()
    run_id = context["ti"].xcom_pull(key="run_id", task_ids="ingest")
    pipeline.db.start_run(run_id, "spark", {"dag": "resora_daily_etl"})
    stats = run_spark_etl(pipeline.config, pipeline.lake, pipeline.db, run_id=run_id, master=Variable.get("spark_master", default_var="local[*]"))
    pipeline.bus.publish("etl.completed", stats)
    return stats["unique_papers"]


def analyze(**context):
    pipeline = _pipeline()
    run_id = context["ti"].xcom_pull(key="run_id", task_ids="ingest")
    return pipeline.analyze(run_id=run_id)["paper_count"]


def index(**context):
    pipeline = _pipeline()
    run_id = context["ti"].xcom_pull(key="run_id", task_ids="ingest")
    manifest = pipeline.build_index(run_id=run_id)
    pipeline.db.finish_run(run_id, status="succeeded", stats={"index": manifest})
    return manifest["papers"]


with DAG(
    dag_id="resora_daily_etl",
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10), "retry_exponential_backoff": True},
    tags=["resora", "big-data"],
) as dag:
    t_ingest = PythonOperator(task_id="ingest", python_callable=ingest)
    t_etl = PythonOperator(task_id="spark_etl", python_callable=etl)
    t_analyze = PythonOperator(task_id="analytics", python_callable=analyze)
    t_index = PythonOperator(task_id="search_index", python_callable=index)
    t_ingest >> t_etl >> t_analyze >> t_index
