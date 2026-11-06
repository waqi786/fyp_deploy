from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.quality.production_env import validate_env_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Resora production environment gates.")
    parser.add_argument("--env-file", default=".env.production.local", help="Path to the production env file.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = ROOT / env_path
    if not env_path.exists():
        print(f"Missing env file: {env_path}", file=sys.stderr)
        return 2

    report = validate_env_file(env_path)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Resora production env ready: {report.ready}")
        print(f"Checked: {report.checked_count} | Blocking: {report.blocking_count} | Warnings: {report.warning_count}")
        for gate in report.gates:
            icon = "PASS" if gate.passed else ("BLOCK" if gate.blocking else "WARN")
            print(f"[{icon}] {gate.name}: {gate.detail}")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
