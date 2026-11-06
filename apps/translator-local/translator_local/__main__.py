from __future__ import annotations

import os
from pathlib import Path

parents = Path(__file__).resolve().parents
repo_root = parents[3] if len(parents) > 3 else Path("/srv")
models_root = Path(os.getenv("RESORA_MODELS_DIR", repo_root / "models"))
os.environ.setdefault("RESORA_MODELS_DIR", str(models_root))
os.environ.setdefault("XDG_DATA_HOME", str(models_root))

import uvicorn

uvicorn.run("app:app", host=os.getenv("LOCAL_TRANSLATOR_HOST", "127.0.0.1"), port=int(os.getenv("LOCAL_TRANSLATOR_PORT", "8091")), workers=1)
