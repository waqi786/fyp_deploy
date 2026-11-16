"""Data Lake (raw, append-only records) and Object Storage (PDFs, figures, tables) on MinIO / S3 or a local folder.

Layout of the lake — raw data is never modified, so everything downstream can be re-processed at any time:

    raw/source=<source>/ingest_date=<YYYY-MM-DD>/run=<run_id>/part-<n>.jsonl.gz     envelopes from the collectors
    curated/papers/run=<run_id>/papers.jsonl.gz                                       deduplicated papers (local engine)
    curated/papers_parquet/                                                           Parquet written by Spark
    analytics/run=<run_id>/analytics.json
    events/<topic>/<YYYY-MM-DD>.jsonl                                                 event log (when Kafka is off)
    state/<collector>.json                                                            incremental cursors

Object storage keeps only binary content; the database stores the key and checksum (the "reference").
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class Storage:
    """Minimal blob storage interface implemented by the local and S3 backends."""

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list(self, prefix: str) -> list[str]: ...
    def url_for(self, key: str, expires: int = 3600) -> str: ...


class LocalStorage(Storage):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key.lstrip("/")).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("key escapes the storage root")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)  # atomic: readers never see half-written files
        return key

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix) if prefix else self.root
        if base.is_file():
            return [prefix]
        if not base.exists():
            return []
        return sorted(str(path.relative_to(self.root)).replace(os.sep, "/") for path in base.rglob("*") if path.is_file() and not path.name.endswith(".tmp"))

    def url_for(self, key: str, expires: int = 3600) -> str:
        return self._path(key).as_uri()


class S3Storage(Storage):  # pragma: no cover - exercised against MinIO in docker-compose, not in unit tests
    def __init__(self, bucket: str, prefix: str, *, endpoint_url: str | None, access_key: str | None, secret_key: str | None, region: str) -> None:
        import boto3  # optional dependency: pip install resora-pipeline[s3]

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", endpoint_url=endpoint_url, aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)
        try:
            self.client.head_bucket(Bucket=bucket)
        except Exception:  # noqa: BLE001
            self.client.create_bucket(Bucket=bucket)

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key.lstrip('/')}" if self.prefix else key.lstrip("/")

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, ContentType=content_type)
        return key

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:  # noqa: BLE001
            return False

    def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
            for item in page.get("Contents", []):
                key = item["Key"][len(self.prefix) + 1:] if self.prefix else item["Key"]
                keys.append(key)
        return sorted(keys)

    def url_for(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": self._key(key)}, ExpiresIn=expires)


def open_storage(uri: str, *, endpoint_url: str | None = None, access_key: str | None = None, secret_key: str | None = None, region: str = "us-east-1") -> Storage:
    parsed = urlparse(uri)
    if parsed.scheme in ("", "file"):
        path = parsed.path if parsed.scheme == "file" else uri
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return LocalStorage(path)
    if parsed.scheme == "s3":
        return S3Storage(parsed.netloc, parsed.path, endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key, region=region)
    raise ValueError(f"Unsupported storage URI scheme: {parsed.scheme}")


class DataLake:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    # ---------------------------------------------------------------- raw zone
    @staticmethod
    def raw_prefix(source: str, ingest_date: str, run_id: str) -> str:
        return f"raw/source={source}/ingest_date={ingest_date}/run={run_id}"

    def write_jsonl(self, key: str, rows: Iterable[dict[str, Any]]) -> int:
        buffer = io.BytesIO()
        count = 0
        with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n")
                count += 1
        self.storage.put_bytes(key, buffer.getvalue(), "application/gzip")
        return count

    def read_jsonl(self, key: str) -> Iterator[dict[str, Any]]:
        data = self.storage.get_bytes(key)
        if key.endswith(".gz"):
            data = gzip.decompress(data)
        for line in data.splitlines():
            if line.strip():
                yield json.loads(line)

    def raw_files(self, *, sources: Iterable[str] | None = None, run_id: str | None = None) -> list[str]:
        wanted = set(sources or [])
        files = []
        for key in self.storage.list("raw/"):
            if not key.endswith(".jsonl.gz"):
                continue
            parts = dict(part.split("=", 1) for part in key.split("/") if "=" in part)
            if wanted and parts.get("source") not in wanted:
                continue
            if run_id and parts.get("run") != run_id:
                continue
            files.append(key)
        return files

    def read_raw(self, **filters: Any) -> Iterator[dict[str, Any]]:
        for key in self.raw_files(**filters):
            yield from self.read_jsonl(key)

    # ---------------------------------------------------------------- state + json helpers
    def write_json(self, key: str, value: Any) -> None:
        self.storage.put_bytes(key, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"), "application/json")

    def read_json(self, key: str, default: Any = None) -> Any:
        if not self.storage.exists(key):
            return default
        return json.loads(self.storage.get_bytes(key))


class ObjectStore:
    """Content-addressed binary storage for PDFs and figures. Returns the reference saved in the database."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def put_pdf(self, data: bytes, *, paper_id: str) -> dict[str, Any]:
        if not data.startswith(b"%PDF-"):
            raise ValueError("not a PDF (magic bytes check failed)")
        checksum = hashlib.sha256(data).hexdigest()
        key = f"pdfs/{checksum[:2]}/{checksum}.pdf"
        if not self.storage.exists(key):
            self.storage.put_bytes(key, data, "application/pdf")
        return {"paper_id": paper_id, "key": key, "sha256": checksum, "bytes": len(data), "content_type": "application/pdf"}

    def get(self, key: str) -> bytes:
        return self.storage.get_bytes(key)

    def url_for(self, key: str, expires: int = 3600) -> str:
        return self.storage.url_for(key, expires)
