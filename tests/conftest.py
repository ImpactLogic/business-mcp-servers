"""
Shared fixtures.

Every fixture redirects the server under test at a tmp_path before the
module is imported, so the suite never reads or writes real user data.
"""

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest

SERVERS = Path(__file__).resolve().parent.parent / "servers"


def load_server(name: str):
    """Import a server module fresh, discarding anything it prints on import."""
    spec = importlib.util.spec_from_file_location(
        f"_srv_{name}", SERVERS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Import under a private name so repeated loads with different env vars
    # do not collide in sys.modules.
    sys.modules[spec.name] = module
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def notes(tmp_path, monkeypatch):
    """Notes server pointed at an empty store."""
    monkeypatch.setenv("NOTES_STORE_PATH", str(tmp_path / "notes"))
    return load_server("notes")


@pytest.fixture
def clipboard(tmp_path, monkeypatch):
    """Clipboard server pointed at an empty history file."""
    monkeypatch.setenv("CLIPBOARD_HISTORY_PATH", str(tmp_path / "history.json"))
    return load_server("clipboard")


@pytest.fixture
def docs():
    """Document manager. Operates on caller-supplied paths, so no env setup."""
    return load_server("document_manager")


@pytest.fixture
def system_info():
    """System info server. Read-only against the host."""
    return load_server("system_info")
