from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from validate_production_env import main as validate_env_main


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Resora pre-deploy launch gates.")
    parser.add_argument("--env-file", default=".env.production.local")
    parser.add_argument("--skip-compose", action="store_true")
    args = parser.parse_args(argv)

    failures = 0
    print("== Resora launch gate: production env ==")
    failures += 0 if validate_env_main(["--env-file", args.env_file]) == 0 else 1

    if not args.skip_compose:
        print("\n== Resora launch gate: docker compose config ==")
        compose = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.prod.yml", "--env-file", args.env_file, "config"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if compose.returncode == 0:
            print("PASS docker compose production config is parseable.")
        else:
            failures += 1
            print("BLOCK docker compose production config failed.")
            print(compose.stderr or compose.stdout)

    if failures:
        print(f"\nResora launch gate failed with {failures} blocking area(s).")
        return 1
    print("\nResora launch gate passed. You can proceed to staging deploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
