from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"


def python_with_pytest_timeout() -> Path | str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
        ROOT.parent.parent / ".venv" / "Scripts" / "python.exe",
        ROOT.parent.parent / ".venv" / "bin" / "python",
    ]
    return next((candidate for candidate in candidates if candidate.is_file()), sys.executable)


if __name__ == "__main__":
    subprocess.run(
        [str(python_with_pytest_timeout()), "-m", "pytest", "app/tests", "-q", "--timeout=60"],
        cwd=API,
        check=True,
    )
