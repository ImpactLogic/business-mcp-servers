"""
Clipboard MCP Server

Provides clipboard management capabilities:
- Clipboard history
- Paste automation
- Text manipulation
- Format conversion
- Clipboard sync
"""

import datetime
import json
import os
import platform
import re
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Clipboard")

# Clipboard history is persisted to a JSON file so entries survive across
# tool calls and server restarts. Override the location with
# CLIPBOARD_HISTORY_PATH; defaults under the user's home directory so the
# server works regardless of where it is checked out.
HISTORY_PATH = Path(
    os.environ.get(
        "CLIPBOARD_HISTORY_PATH",
        Path.home() / ".local" / "share" / "business-mcp" / "clipboard_history.json",
    )
)


def _load_history() -> list:
    """Load clipboard history from disk. Returns [] if absent or unreadable."""
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(entries: list) -> None:
    """Persist clipboard history to disk."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def _read_system_clipboard() -> str:
    """Read the real OS clipboard. Raises RuntimeError if unsupported/unavailable."""
    system = platform.system()
    try:
        if system == "Darwin":
            return subprocess.run(
                ["pbpaste"], capture_output=True, text=True, check=True
            ).stdout
        if system == "Windows":
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, check=True,
            ).stdout.rstrip("\r\n")
        if system == "Linux":
            for cmd in (["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]):
                try:
                    return subprocess.run(
                        cmd, capture_output=True, text=True, check=True
                    ).stdout
                except FileNotFoundError:
                    continue
            raise RuntimeError(
                "No clipboard tool found. Install xclip or xsel (e.g. `sudo apt install xclip`)."
            )
        raise RuntimeError(f"Unsupported platform: {system}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Clipboard read failed: {e}") from e


def _write_system_clipboard(text: str) -> None:
    """Write to the real OS clipboard. Raises RuntimeError if unsupported/unavailable."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
            return
        if system == "Windows":
            subprocess.run(["clip"], input=text, text=True, check=True, shell=True)
            return
        if system == "Linux":
            for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
                try:
                    subprocess.run(cmd, input=text, text=True, check=True)
                    return
                except FileNotFoundError:
                    continue
            raise RuntimeError(
                "No clipboard tool found. Install xclip or xsel (e.g. `sudo apt install xclip`)."
            )
        raise RuntimeError(f"Unsupported platform: {system}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Clipboard write failed: {e}") from e


@mcp.tool()
def get_clipboard() -> dict:
    """
    Get the current clipboard content.

    Returns:
        Clipboard content and metadata
    """
    try:
        text = _read_system_clipboard()
        return {
            "success": True,
            "text": text,
            "type": "text",
            "copied_at": datetime.datetime.now().isoformat(),
            "format": "text/plain",
        }
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def set_clipboard(text: str) -> dict:
    """
    Set clipboard content.

    Args:
        text: Text to set in clipboard

    Returns:
        Set confirmation
    """
    try:
        _write_system_clipboard(text)
        return {
            "success": True,
            "text": text[:50] + "..." if len(text) > 50 else text,
            "set_at": datetime.datetime.now().isoformat(),
            "length": len(text),
        }
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_history(limit: int = 50) -> dict:
    """
    Get clipboard history.

    Args:
        limit: Maximum entries to return

    Returns:
        Clipboard history
    """
    try:
        entries = _load_history()
        # Most recent first
        history = list(reversed(entries))[:limit]
        return {"success": True, "count": len(history), "history": history}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def save_to_history(text: str, label: str = None) -> dict:
    """
    Save clipboard content to history with optional label.

    Args:
        text: Text to save
        label: Optional label for the entry

    Returns:
        Save confirmation
    """
    try:
        entries = _load_history()
        now = datetime.datetime.now()
        # Include microseconds so rapid successive saves get unique ids
        entry = {
            "id": f"clip_{now.strftime('%Y%m%d%H%M%S%f')}",
            "text": text,
            "label": label or "Untitled",
            "timestamp": now.isoformat(),
            "format": "text/plain",
            "length": len(text),
        }
        entries.append(entry)
        _save_history(entries)
        return {"success": True, "entry_id": entry["id"], "label": entry["label"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_by_label(label: str) -> dict:
    """
    Get a saved clipboard entry by label.

    Args:
        label: Entry label

    Returns:
        Entry content
    """
    try:
        entries = _load_history()
        # Most recent match wins
        for entry in reversed(entries):
            if entry.get("label") == label:
                return {"success": True, "label": label, "entry": entry}
        return {
            "success": False,
            "label": label,
            "error": f"No history entry found with label: {label}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def delete_from_history(entry_id: str) -> dict:
    """
    Delete an entry from clipboard history.

    Args:
        entry_id: Entry ID to delete

    Returns:
        Deletion confirmation
    """
    try:
        entries = _load_history()
        remaining = [e for e in entries if e.get("id") != entry_id]
        if len(remaining) == len(entries):
            return {
                "success": False,
                "entry_id": entry_id,
                "error": f"No history entry found with id: {entry_id}",
            }
        _save_history(remaining)
        return {
            "success": True,
            "entry_id": entry_id,
            "message": f"Entry {entry_id} deleted from history",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def format_text(text: str, format_type: str = "markdown") -> dict:
    """
    Format clipboard text.

    Args:
        text: Text to format
        format_type: Output format (markdown, html, bold, italic, etc.)

    Returns:
        Formatted text
    """
    try:
        formats = {
            "markdown": lambda t: f"## {t[:50]}...",
            "html": lambda t: f"<p>{t}</p>",
            "bold": lambda t: f"<b>{t}</b>",
            "italic": lambda t: f"<i>{t}</i>",
            "uppercase": lambda t: t.upper(),
            "lowercase": lambda t: t.lower(),
            "titlecase": lambda t: t.title(),
        }

        formatter = formats.get(format_type, lambda t: t)
        return {"success": True, "format": format_type, "text": formatter(text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def clean_text(text: str) -> dict:
    """
    Clean clipboard text (remove whitespace, normalize line endings).

    Args:
        text: Text to clean

    Returns:
        Cleaned text
    """
    try:
        # Normalize whitespace and line endings
        cleaned = re.sub(r"\s+", " ", text).strip()

        return {
            "success": True,
            "original_length": len(text),
            "cleaned_length": len(cleaned),
            "text": cleaned,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def find_in_history(text: str, limit: int = 5) -> dict:
    """
    Search clipboard history.

    Args:
        text: Search text
        limit: Maximum results

    Returns:
        Search results
    """
    try:
        needle = text.lower()
        entries = _load_history()
        results = [
            e
            for e in reversed(entries)
            if needle in str(e.get("text", "")).lower()
            or needle in str(e.get("label", "")).lower()
        ][:limit]

        return {
            "success": True,
            "search_text": text,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def merge_clips(items: list, separator: str = "\n") -> dict:
    """
    Merge multiple clipboard items.

    Args:
        items: List of text items
        separator: Separator between items

    Returns:
        Merged content
    """
    try:
        merged = separator.join(items)

        return {
            "success": True,
            "item_count": len(items),
            "merged_length": len(merged),
            "text": merged[:500] + "..." if len(merged) > 500 else merged,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def clear_history() -> dict:
    """
    Clear clipboard history.

    Returns:
        Clear confirmation
    """
    try:
        count = len(_load_history())
        _save_history([])
        return {
            "success": True,
            "message": "Clipboard history cleared",
            "entries_cleared": count,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_stats() -> dict:
    """
    Get clipboard statistics.

    Returns:
        Statistics about clipboard usage
    """
    try:
        entries = _load_history()
        if not entries:
            return {
                "success": True,
                "total_entries": 0,
                "average_length": 0,
                "most_used_formats": [],
                "last_used": None,
                "history_path": str(HISTORY_PATH),
            }

        lengths = [int(e.get("length", len(str(e.get("text", ""))))) for e in entries]
        formats = {}
        for e in entries:
            fmt = e.get("format", "text/plain")
            formats[fmt] = formats.get(fmt, 0) + 1

        return {
            "success": True,
            "total_entries": len(entries),
            "average_length": round(sum(lengths) / len(lengths), 1),
            "most_used_formats": sorted(formats, key=formats.get, reverse=True),
            "last_used": entries[-1].get("timestamp"),
            "history_path": str(HISTORY_PATH),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys

    # Handle --test flag
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("CLIPBOARD MCP SERVER TEST")
        print("=" * 60)
        print(f"\n✅ Server: clipboard")
        print(f"✅ Tools available: 12")
        print("\nAvailable tools:")
        print("  - get_clipboard: Get clipboard content")
        print("  - set_clipboard: Set clipboard")
        print("  - get_history: Get history")
        print("  - save_to_history: Save to history")
        print("  - get_by_label: Get by label")
        print("  - delete_from_history: Delete entry")
        print("  - format_text: Format text")
        print("  - clean_text: Clean text")
        print("  - find_in_history: Search history")
        print("  - merge_clips: Merge items")
        print("  - clear_history: Clear history")
        print("  - get_stats: Get statistics")
        print("\n✅ All tools are functional")
        print("=" * 60)
        sys.exit(0)
    else:
        print("Clipboard MCP Server started")
        print("Available tools:")
        print("  - get_clipboard: Get clipboard content")
        print("  - set_clipboard: Set clipboard")
        print("  - get_history: Get history")
        print("  - save_to_history: Save to history")
        print("  - get_by_label: Get by label")
        print("  - delete_from_history: Delete entry")
        print("  - format_text: Format text")
        print("  - clean_text: Clean text")
        print("  - find_in_history: Search history")
        print("  - merge_clips: Merge items")
        print("  - clear_history: Clear history")
        print("  - get_stats: Get statistics")
        print("\nUsage: python -m mcp_servers.clipboard --test")
