import argparse
import json
from pathlib import Path

from app.schemas.developer import DeveloperPlatformRequest
from app.services.developer.platform import DeveloperPlatformService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resora")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_refs = subparsers.add_parser("import-refs")
    import_refs.add_argument("--format", choices=["json", "csv"], required=True)
    import_refs.add_argument("--input", required=True)

    subparsers.add_parser("admin-summary")

    args = parser.parse_args(argv)
    service = DeveloperPlatformService()

    if args.command == "import-refs":
        blob = Path(args.input).read_text(encoding="utf-8")
        response = service.build(
            DeveloperPlatformRequest(
                user_id="cli-user",
                workspace_id="cli-workspace",
                reference_blob=blob,
                reference_format=args.format,
            )
        )
        print(json.dumps([paper.model_dump() for paper in response.imported_references], indent=2))
        return 0

    if args.command == "admin-summary":
        response = service.build(DeveloperPlatformRequest(user_id="cli-user", workspace_id="cli-workspace"))
        print(json.dumps(response.admin_dashboard.model_dump(), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
