import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An isolated project root with the real config/ and an empty data/."""
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    monkeypatch.setenv("TTG_ROOT", str(tmp_path))
    return tmp_path
