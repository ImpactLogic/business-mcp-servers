# Business MCP Servers

Four [Model Context Protocol](https://modelcontextprotocol.io) servers that give Claude
access to your local machine: clipboard, notes, files, and system state.

**41 tools. Pure Python. No API keys, no accounts, no cloud, no telemetry.**

---

## Why another MCP server collection

Because I checked whether mine actually worked, and a third of them didn't.

I wrote 27 MCP servers. When I audited them properly — calling every tool
with real input and inspecting the real output, instead of just confirming
they imported — **8 turned out to be fabrications.** They returned
`success: True` while doing nothing at all. The worst was a "PDF redactor"
that never opened the PDF and reported `items_redacted: 3`. Anyone
trusting it would have shared an unredacted document believing it was
scrubbed.

I deleted those 8 and fixed 17 real bugs in the rest.

**Every server here was verified by running it.** Each section below
states exactly what was tested and how, so you can re-run it yourself.

This matters more than usual right now. A lot of MCP servers are being
generated fast and published unrun. Compiling, importing, and registering
tools are *not* evidence a server works — all three passed on every one of
my fakes.

---

## The servers

### `system_info` — 14 tools

Real hardware and OS state: CPU load and core counts, memory and swap,
disk partitions and usage, network interfaces, running processes,
uptime, Python environment.

> "How much disk space is left, and what's using the most memory?"

*Verified: returns live values that change between calls and match
`top`/`df`.* Pure stdlib + `psutil`.

### `clipboard` — 12 tools

Your **real** OS clipboard, plus a searchable history that persists across
restarts. Read and write the clipboard, save entries under labels, search
history, merge multiple clips, clean up whitespace, convert formats.

> "Save that to my clipboard history as 'api-notes', then find the clip I
> saved about the database schema."

*Verified: round-trip write→read against the real system clipboard;
history persisted to disk, searched, deleted, and cleared.* Uses
`pbcopy`/`pbpaste` on macOS, PowerShell on Windows, `xclip`/`xsel` on
Linux. Zero dependencies.

**Note:** this one was previously fake — it returned the string
`"Sample clipboard text"` for every read. It has been rewritten.

### `notes` — 9 tools

Persistent notes with tags, search, and export. Create, retrieve, list,
tag, search, delete, import, and export.

> "Make a note of these three decisions and tag it 'architecture'."

*Verified: created notes, re-read them in a separate call, confirmed
they persisted to disk.* Zero dependencies.

### `document-manager-server` — 6 tools

File management: metadata inspection, bulk organization by rules,
archiving, listing with filters.

> "Organize everything in ~/Downloads into folders by file type."

*Verified: real metadata (size, timestamps, permissions) on real files;
organize and archive operations produce actual results on disk.* Zero
dependencies.

---

## Install

Python 3.10+.

```bash
git clone https://github.com/ImpactLogic/business-mcp-servers.git
cd business-mcp-servers
pip install -r requirements.txt
```

Register the ones you want. For **Claude Desktop**, edit
`claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "clipboard": {
      "command": "python",
      "args": ["/absolute/path/to/business-mcp-servers/servers/clipboard.py"]
    },
    "notes": {
      "command": "python",
      "args": ["/absolute/path/to/business-mcp-servers/servers/notes.py"]
    },
    "system-info": {
      "command": "python",
      "args": ["/absolute/path/to/business-mcp-servers/servers/system_info.py"]
    },
    "document-manager": {
      "command": "python",
      "args": ["/absolute/path/to/business-mcp-servers/servers/document-manager-server.py"]
    }
  }
}
```

Use absolute paths, and restart Claude. Each server is standalone — add
only what you want, in any combination.

For **Claude Code**:

```bash
claude mcp add clipboard -- python /absolute/path/to/servers/clipboard.py
```

---

## Where your data lives

Servers that persist data write to `~/.local/share/business-mcp/` —
never inside this repo, never to a hardcoded path.

| Server | Override with |
|---|---|
| `clipboard` | `CLIPBOARD_HISTORY_PATH` |

Nothing leaves your machine. No telemetry, no network calls, no analytics.

---

## Verify it yourself

Don't take my word for it — that's the entire point.

**Structural check** (necessary, not sufficient):

```bash
python - <<'PY'
import importlib.util, pathlib, io, contextlib, asyncio
for p in sorted(pathlib.Path("servers").glob("*.py")):
    spec = importlib.util.spec_from_file_location(p.stem.replace("-","_"), p)
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(m)
    print(f"{p.name:28} {len(asyncio.run(m.mcp.list_tools()))} tools")
PY
```

Expect `41 tools` across 4 servers.

**The check that actually matters** — call a tool and look at the output.
For anything stateful, *write then read back*:

```python
m.create_note(title="test", content="hello")
m.list_notes()      # must contain what you just wrote
```

If step 2 comes back empty, the server isn't persisting. That was true of
several of mine before I fixed them, and it's the single most useful test
you can run against any MCP server — including ones you didn't write.

---

## Requirements

`mcp` for all servers, plus `psutil` for `system_info`. The other three
are pure standard library.

Linux users: `clipboard` needs `xclip` or `xsel` installed. macOS and
Windows work out of the box.

---

## Contributing

Bug reports welcome — especially **"this tool returns success but doesn't
do the thing."** That's the failure mode I care most about. If you open a
PR, please say how you tested it.

## License

MIT — see [LICENSE](LICENSE).
