"""Importing the app must not need any running service (database, Qdrant, Redis, Ollama)."""

import os
import subprocess
import sys

from tests.conftest import BACKEND_DIR


def test_app_imports_without_a_database():
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://nobody:nothing@127.0.0.1:1/none",   # nothing listens on port 1
        "QDRANT_URL": "http://127.0.0.1:1",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-W", "ignore", "-c",
         "import app.main as m; print(sorted({r.path for r in m.app.routes if hasattr(r, 'path')})[:3])"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-1500:]


def test_removed_modules_are_really_gone():
    import importlib.util

    assert importlib.util.find_spec("app.generation.memory") is None
    assert importlib.util.find_spec("app.augmentation.prompt_template") is None
