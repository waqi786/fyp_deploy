"""Pipeline configuration from environment variables (never hard-code keys; see .env.example).

LAKE_URI            file:///abs/path/lake  (default: ./data/lake)  or  s3://resora-lake  (MinIO / S3)
OBJECT_STORE_URI    file:///abs/path/objects (default: ./data/objects) or s3://resora-objects
S3_ENDPOINT_URL     http://minio:9000 for MinIO (omit for AWS S3)
S3_ACCESS_KEY / S3_SECRET_KEY / S3_REGION
CATALOG_DATABASE_URL  sqlite:///./data/catalog.sqlite3 (default) or postgresql://user:pass@host/db
PIPELINE_OUTPUT_DIR   where analytics JSON + the search index are written (default ./data/output)
CONTACT_EMAIL       polite-pool contact for OpenAlex / Crossref (placeholder in examples, real value only in .env)
SEMANTIC_SCHOLAR_API_KEY  optional; raises the Semantic Scholar rate limit
KAFKA_BOOTSTRAP_SERVERS   optional; enables the Kafka event bus (otherwise events go to the lake + in-process)
EMBEDDER              hash-v1 (default, no downloads) or st:<sentence-transformers model name>
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_dir(name: str) -> str:
    return (Path.cwd() / "data" / name).resolve().as_uri()


@dataclass(frozen=True)
class PipelineConfig:
    lake_uri: str = field(default_factory=lambda: os.getenv("LAKE_URI") or _default_dir("lake"))
    object_store_uri: str = field(default_factory=lambda: os.getenv("OBJECT_STORE_URI") or _default_dir("objects"))
    s3_endpoint_url: str | None = field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL") or None)
    s3_access_key: str | None = field(default_factory=lambda: os.getenv("S3_ACCESS_KEY") or None)
    s3_secret_key: str | None = field(default_factory=lambda: os.getenv("S3_SECRET_KEY") or None)
    s3_region: str = field(default_factory=lambda: os.getenv("S3_REGION", "us-east-1"))
    catalog_database_url: str = field(default_factory=lambda: os.getenv("CATALOG_DATABASE_URL") or f"sqlite:///{(Path.cwd() / 'data' / 'catalog.sqlite3').resolve()}")
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("PIPELINE_OUTPUT_DIR") or (Path.cwd() / "data" / "output")).resolve())
    contact_email: str = field(default_factory=lambda: os.getenv("CONTACT_EMAIL", "research@example.org"))
    semantic_scholar_api_key: str | None = field(default_factory=lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None)
    kafka_bootstrap_servers: str | None = field(default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS") or None)
    embedder: str = field(default_factory=lambda: os.getenv("EMBEDDER", "hash-v1"))
    user_agent: str = "ResoraResearchPipeline/1.0 (+https://resora.app; academic research platform)"

    def redacted(self) -> dict[str, object]:
        """Safe to log: secrets are never included."""
        return {
            "lake_uri": self.lake_uri, "object_store_uri": self.object_store_uri, "s3_endpoint_url": self.s3_endpoint_url,
            "catalog_database": self.catalog_database_url.split("@")[-1], "output_dir": str(self.output_dir),
            "kafka": bool(self.kafka_bootstrap_servers), "embedder": self.embedder,
            "semantic_scholar_key": bool(self.semantic_scholar_api_key),
        }
