"""Command line entry point.

    python -m resora_pipeline run --query "vision language hallucination" --sources openalex,arxiv,crossref --max 300
    python -m resora_pipeline run --engine spark --skip-ingest          # re-process everything already in the lake
    python -m resora_pipeline etl | analyze | index                       # run one stage
    python -m resora_pipeline status                                      # recent runs and catalog size
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from resora_pipeline.config import PipelineConfig
from resora_pipeline.orchestrator import Pipeline, new_run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resora_pipeline", description="Resora research data pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="collect → ETL → analytics → index")
    run.add_argument("--query", action="append", default=[], help="search query (repeatable)")
    run.add_argument("--sources", default="openalex,arxiv,crossref,semantic_scholar")
    run.add_argument("--max", type=int, default=200, help="max records per source and query")
    run.add_argument("--since", default=None, help="only records updated since YYYY-MM-DD (default: last successful run)")
    run.add_argument("--engine", choices=("local", "spark"), default="local")
    run.add_argument("--skip-ingest", action="store_true")
    for name in ("etl", "analyze", "index", "status"):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    pipeline = Pipeline(PipelineConfig())
    if args.command == "run":
        if not args.query and not args.skip_ingest:
            parser.error("--query is required unless --skip-ingest is used")
        result = pipeline.run(queries=args.query, sources=[s.strip() for s in args.sources.split(",") if s.strip()], engine=args.engine, max_records=args.max, since=args.since, skip_ingest=args.skip_ingest)
    elif args.command == "etl":
        _, result = pipeline.etl_local(run_id=new_run_id())
    elif args.command == "analyze":
        result = {k: (v if k == "paper_count" else len(v)) for k, v in pipeline.analyze(run_id=new_run_id()).items()}
    elif args.command == "index":
        result = pipeline.build_index(run_id=new_run_id())
    else:
        result = {"papers": pipeline.db.count(), "runs": pipeline.db.runs(5), "config": pipeline.config.redacted()}
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
