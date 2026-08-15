"""
Startup smoke tests.

This is the check the README's structural snippet could not perform. That
snippet imported each module and counted registered tools, which passed
cleanly the entire time no server in this repo was capable of starting:
every __main__ block printed a banner and exited, so Claude Desktop
received human-readable text where the JSON-RPC handshake belonged.

Importing a module and registering tools is not evidence a server runs.
Speaking protocol over stdio is.
"""

import json
import os
import subprocess
import sys

import pytest

from conftest import SERVERS

SERVER_NAMES = ["clipboard", "notes", "system_info", "document_manager"]

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}


def _initialize(name, tmp_path):
    """Start a server over stdio and return its parsed initialize response."""
    # Extend the real environment rather than replacing it: a hardcoded
    # Unix-style PATH here broke Python's own import machinery on Windows
    # (SystemRoot and friends are required for the mcp package to import),
    # so every server "failed to start" for a reason that had nothing to do
    # with the server code.
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["NOTES_STORE_PATH"] = str(tmp_path / "notes")
    env["CLIPBOARD_HISTORY_PATH"] = str(tmp_path / "clip.json")
    process = subprocess.run(
        [sys.executable, str(SERVERS / f"{name}.py")],
        input=json.dumps(INITIALIZE) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=tmp_path,
    )
    return process


@pytest.mark.parametrize("name", SERVER_NAMES)
def test_server_answers_initialize_over_stdio(name, tmp_path):
    process = _initialize(name, tmp_path)

    first_line = process.stdout.strip().split("\n")[0] if process.stdout else ""
    assert first_line, f"{name} wrote nothing to stdout. stderr: {process.stderr[:500]}"

    try:
        response = json.loads(first_line)
    except json.JSONDecodeError:
        pytest.fail(
            f"{name} wrote non-JSON to the stdio transport, so no MCP client "
            f"can talk to it. First line was: {first_line[:200]!r}"
        )

    assert response.get("jsonrpc") == "2.0"
    assert "result" in response, response
    assert response["result"]["serverInfo"]["name"]


@pytest.mark.parametrize("name", SERVER_NAMES)
def test_server_does_not_print_banners_to_stdout(name, tmp_path):
    """
    stdout is the transport. Anything printed there that is not JSON-RPC
    corrupts the stream, which is precisely how the old __main__ blocks
    broke every install.
    """
    process = _initialize(name, tmp_path)

    for line in process.stdout.splitlines():
        if line.strip():
            json.loads(line)


@pytest.mark.parametrize("name", SERVER_NAMES)
def test_server_module_has_no_test_flag(name):
    """
    Regression: each server had a --test flag that printed
    "All tools are functional" without executing any tool code. It passed
    while export_notes, get_disk_info and get_network_info were all broken.
    """
    source = (SERVERS / f"{name}.py").read_text()
    assert "--test" not in source
    assert "All tools are functional" not in source


def test_all_servers_are_registered_in_the_readme():
    """The install instructions must cover every server that exists."""
    readme = (SERVERS.parent / "README.md").read_text()
    for name in SERVER_NAMES:
        assert f"servers/{name}.py" in readme, f"{name} missing from README install"
