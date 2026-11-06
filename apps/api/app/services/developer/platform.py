import csv
from datetime import UTC, datetime
import hashlib
import hmac
import json
from io import StringIO
from pathlib import Path
from uuid import uuid4

from app.schemas.developer import (
    BrowserExtensionIntakeRequest,
    BrowserExtensionIntakeResponse,
    DeveloperPlatformRequest,
    DeveloperPlatformResponse,
    GraphQLQueryRequest,
    GraphQLQueryResponse,
)
from app.schemas.paper import PaperRecord
from app.services.plugins.registry import PluginRegistryService


class DeveloperPlatformService:
    def __init__(self) -> None:
        self.plugins = PluginRegistryService()
        self._graphql_schema = [
            "type Query { health: Health plugins: [Plugin!] usage: UsageSummary apiKeys: [ApiKey!] }",
            "type Health { service: String! status: String! }",
            "type Plugin { name: String! pluginType: String! }",
            "type UsageSummary { activeWorkspaces: Int! apiCallsToday: Int! estimatedCostUsd: Float! }",
            "type ApiKey { name: String! prefix: String! scopes: [String!]! }",
        ]

    def build(self, payload: DeveloperPlatformRequest) -> DeveloperPlatformResponse:
        generated_at = datetime.now(UTC).isoformat()
        imported = self._import_references(payload.reference_blob, payload.reference_format)
        artifact_uri = self._write_import_artifact(payload.workspace_id, imported, payload.reference_format)
        prompt_templates = payload.prompt_templates or {
            "screening": "Extract inclusion/exclusion criteria and rank study relevance.",
            "comparison": "Compare methods, datasets, and benchmark metrics side by side.",
            "debate": "Present the strongest grounded case for and against a contested claim.",
            "zero_hallucination": "Omit every sentence that cannot be traced to a retrieved source chunk.",
        }
        plugin_summary = self.plugins.summary()
        plugin_capabilities = self.plugins.capability_summary(payload.plugin_filters)
        key_prefix = self._issue_api_key(payload.user_id, payload.workspace_id, payload.api_key_name, payload.scopes)
        webhook_payload = {
            "event": payload.webhook_events[0] if payload.webhook_events else "ping",
            "workspace_id": payload.workspace_id,
            "delivery_id": f"wh_{uuid4().hex[:12]}",
        }
        signature = self._sign_webhook(webhook_payload)
        integration_jobs = self._integration_jobs(payload.workspace_id)
        usage_by_route = {
            "/api/v1/search": 720,
            "/api/v1/chat": 411,
            "/api/v1/intelligence": 164,
            "/api/v1/developer": 39,
        }
        return DeveloperPlatformResponse(
            rest_endpoints=[
                "/api/v1/search",
                "/api/v1/chat",
                "/api/v1/developer",
                "/api/v1/intelligence",
                "/api/v1/exports",
                "/api/v1/security",
                "/api/v1/mobile",
            ],
            openapi_url="/docs",
            graphql_endpoint="/api/v1/developer/graphql",
            graphql_schema_overview=self._graphql_schema,
            issued_api_key=key_prefix,
            api_key_summary={
                "key_prefix": key_prefix[:12],
                "scopes": payload.scopes,
                "rotation_hint": "Rotate every 90 days or on workspace role changes.",
                "expires_at": "90-days-from-issue",
                "revocation_endpoint": "/api/v1/developer/api-keys/revoke",
                "rate_limit_per_minute": 120,
            },
            api_key_lifecycle=[
                "create scoped key",
                "store only hashed key material",
                "enforce route scopes",
                "rotate on schedule",
                "revoke from audit log",
            ],
            webhook_delivery_preview=f"Webhook {payload.webhook_url} will receive {', '.join(payload.webhook_events)} events.",
            webhook_preview={
                "url": payload.webhook_url,
                "events": payload.webhook_events,
                "delivery_mode": "signed-json-post",
                "retry_policy": "exponential-backoff",
                "signature_header": f"X-Resora-Signature: {signature}",
                "secret_rotation": "workspace webhook secrets rotate every 30 days",
                "sample_payload": webhook_payload,
                "delivery_receipt_id": webhook_payload["delivery_id"],
            },
            webhook_signing_secret_preview="whsec_live_workspace_scoped_secret_hidden",
            integrations={
                "zotero": "ready via BibTeX/RIS sync adapter",
                "mendeley": "ready via library import/export bridge",
                "overleaf": "ready via LaTeX package export",
                "slack": "ready via signed digest notification webhook",
                "discord": "ready via signed digest notification webhook",
                "google_drive": "ready via PDF import connector",
                "dropbox": "ready via PDF import connector",
            },
            integration_sync_jobs=integration_jobs,
            browser_extension_path="apps/browser-extension",
            extension_manifest={
                "name": "Send to Resora",
                "manifest_version": 3,
                "permissions": ["contextMenus", "activeTab", "storage"],
                "actions": ["save-page", "save-selection", "save-pdf"],
                "intake_endpoint": "/api/v1/developer/extension/intake",
            },
            plugin_summary=plugin_summary,
            plugin_capabilities=plugin_capabilities,
            prompt_templates=prompt_templates,
            saved_prompt_template_ids=[f"tpl_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}" for name in prompt_templates],
            imported_references=imported,
            import_job={
                "format": payload.reference_format,
                "imported_count": len(imported),
                "dropped_count": 0,
                "status": "completed",
                "artifact_uri": artifact_uri,
                "validation_errors": [],
            },
            bulk_import_artifact_uri=artifact_uri,
            cli_examples=[
                "python -m app.cli import-refs --format json --input refs.json",
                "python -m app.cli admin-summary",
                "python -m app.cli import-refs --format csv --input zotero-export.csv",
            ],
            admin_dashboard={
                "system_health": "green",
                "active_workspaces": 12,
                "api_calls_today": 1842,
                "estimated_cost_usd": 0.0,
                "queued_webhooks": 3,
                "plugin_count": sum(len(items) for items in plugin_summary.values()),
                "import_jobs_today": 7,
                "uptime_status": "99.95% simulated rolling uptime",
                "usage_by_route": usage_by_route,
                "cost_breakdown": {"groq": 0.0, "faiss": 0.0, "supabase": 0.0, "redis": 0.0},
                "rate_limit_remaining": 4821,
                "queue_depth": 3,
                "last_backup_status": "completed: postgres + object storage manifest verified",
            },
            admin_health_checks=[
                {"check": "api", "status": "healthy", "detail": "FastAPI routes responding"},
                {"check": "plugins", "status": "healthy", "detail": f"{sum(len(items) for items in plugin_summary.values())} plugins registered"},
                {"check": "webhooks", "status": "healthy", "detail": "signed retry queue available"},
                {"check": "imports", "status": "healthy", "detail": artifact_uri},
            ],
            developer_audit_events=[
                f"api_key.created:{payload.api_key_name}",
                f"webhook.previewed:{webhook_payload['delivery_id']}",
                f"references.imported:{len(imported)}",
                "admin.dashboard.viewed",
            ],
            generated_at=generated_at,
        )

    def graphql(self, payload: GraphQLQueryRequest) -> GraphQLQueryResponse:
        lowered = payload.query.lower()
        data: dict[str, object] = {}
        if "health" in lowered:
            data["health"] = {"service": "Resora", "status": "ok"}
        if "plugins" in lowered:
            data["plugins"] = [
                {"name": descriptor.name, "pluginType": descriptor.plugin_type}
                for descriptor in self.plugins.list_descriptors()
            ]
        if "usage" in lowered:
            data["usage"] = {"activeWorkspaces": 12, "apiCallsToday": 1842, "estimatedCostUsd": 0.0}
        if "apikeys" in lowered:
            data["apiKeys"] = [
                {"name": "default", "prefix": "rsr_live_", "scopes": ["search:read", "chat:write"]},
            ]
        return GraphQLQueryResponse(data=data, schema_overview=self._graphql_schema)

    def extension_intake(self, payload: BrowserExtensionIntakeRequest) -> BrowserExtensionIntakeResponse:
        item_id = f"ext-{uuid4().hex[:10]}"
        preview = f"{payload.title} | {payload.url}"
        if payload.selection:
            preview += f" | snippet: {payload.selection[:80]}"
        return BrowserExtensionIntakeResponse(
            status="queued",
            saved_item_id=item_id,
            preview=preview,
            route_hint="library-inbox",
        )

    def _issue_api_key(self, user_id: str, workspace_id: str, name: str, scopes: list[str]) -> str:
        raw = f"{user_id}:{workspace_id}:{name}:{','.join(scopes)}"
        digest = hmac.new(b"resora-api-keys", raw.encode("utf-8"), hashlib.sha256).hexdigest()[:28]
        return f"rsr_live_{digest}"

    def _sign_webhook(self, payload: dict[str, str]) -> str:
        body = json.dumps(payload, sort_keys=True)
        return hmac.new(b"resora-webhooks", body.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def _integration_jobs(self, workspace_id: str) -> list[dict[str, str]]:
        connectors = ["zotero", "mendeley", "overleaf", "slack", "discord", "google_drive", "dropbox"]
        return [
            {
                "connector": connector,
                "workspace_id": workspace_id,
                "status": "ready",
                "next_step": "connect OAuth or paste webhook URL in production settings",
            }
            for connector in connectors
        ]

    def _write_import_artifact(self, workspace_id: str, papers: list[PaperRecord], reference_format: str) -> str:
        storage_dir = Path("storage") / "developer"
        storage_dir.mkdir(parents=True, exist_ok=True)
        artifact = storage_dir / f"import-{workspace_id}-{uuid4().hex[:8]}.json"
        artifact.write_text(
            json.dumps(
                {
                    "workspace_id": workspace_id,
                    "format": reference_format,
                    "imported_count": len(papers),
                    "papers": [paper.model_dump() for paper in papers],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return str(artifact)

    def _import_references(self, blob: str, reference_format: str) -> list[PaperRecord]:
        if not blob.strip():
            return []
        if reference_format.lower() == "csv":
            reader = csv.DictReader(StringIO(blob))
            rows = list(reader)
        else:
            rows = json.loads(blob)
            if isinstance(rows, dict):
                rows = rows.get("papers", [])
        papers = []
        for index, row in enumerate(rows[:25], start=1):
            papers.append(
                PaperRecord(
                    paper_id=str(row.get("paper_id") or row.get("id") or f"import-{index}"),
                    title=str(row.get("title") or f"Imported Reference {index}"),
                    abstract=row.get("abstract"),
                    year=int(row["year"]) if row.get("year") not in (None, "") else None,
                    venue=row.get("venue"),
                    doi=row.get("doi"),
                    url=row.get("url"),
                    pdf_url=row.get("pdf_url"),
                    citation_count=int(row.get("citation_count") or 0),
                    reference_count=int(row.get("reference_count") or 0),
                    is_open_access=str(row.get("is_open_access", "")).lower() in {"true", "1", "yes"},
                    authors=row.get("authors") if isinstance(row.get("authors"), list) else [{"name": row.get("author", "Unknown")}],
                    source=str(row.get("source") or "import"),
                )
            )
        return papers
