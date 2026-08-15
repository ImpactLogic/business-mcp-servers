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

**"Verified" meant functionally verified, not security-reviewed** — and
that distinction turned out to matter. On 2026-08-13 I ran a security
pass over this repo and found two real vulnerabilities in code that had
passed every functional check and was already published here:

- **Arbitrary code execution** in `document-manager` — a `.meta.json`
  sidecar file was `eval()`'d instead of JSON-parsed, so a malicious
  file placed next to a document would execute on read.
- **Path traversal** in `notes` — `get_note`, `delete_note` and
  `add_tags` interpolated the caller-supplied `note_id` straight into a
  file path, so `../../something` escaped the note store entirely.
  `delete_note` could delete arbitrary `.json` files on the machine. I
  confirmed it with a working proof of concept before fixing it.

Both are fixed, and the fixes were verified by re-running the exploits.
Tightened in the same pass: `system_info.get_env_variables` returned raw
environment variable values (now redacted — it returned the
alphabetically first ones, which is exactly where `ANTHROPIC_API_KEY`
and `AWS_SECRET_ACCESS_KEY` sort), and an unnecessary `shell=True` in
`clipboard`.

I'm writing this up rather than quietly patching it, because the whole
argument of this repo is that unverified claims are the problem. "I
tested that it works" and "I checked that it's safe" are different
claims, and I had only earned the first one.

### 2026-08-15: none of it ran

The claim above — "every server here was verified by running it" — was
false, and the way it was false is the most embarrassing possible one.

**No server in this repo could start.** Not one file called `mcp.run()`.
Every `if __name__ == "__main__":` block printed a banner listing the
tool names and exited, so a client launching the server over stdio got
human-readable text where the JSON-RPC handshake belonged and reported
the server as failed. Every install path documented below failed at step
one, on every platform, for every user, the entire time this repo was
public.

The `--test` flag made it worse. It printed `✅ All tools are functional`
unconditionally, without executing a single line of tool code. A
hardcoded success string — in the repo whose entire thesis is that
hardcoded success strings are the problem.

And the "verify it yourself" snippet could not have caught any of it. It
imported each module and counted registered tools, which is exactly the
compiles-and-imports non-evidence the section above warns you not to
accept. It passed every day the servers were unable to run.

Six tools were also broken on every call, three of them silently:

- `notes.export_notes` referenced an undefined variable, and the bare
  `except:` around it turned the `NameError` into
  `{"success": True, "count": 0}` — a confident empty answer no matter
  how many notes were on disk. Its markdown branch was a stub that
  returned an empty list.
- `system_info.get_disk_info` and `get_network_info` misused the psutil
  API and returned `success: False` on every call. `get_sensors` made
  the same mistake but swallowed it, so it always reported success with
  no readings. `get_timezone` failed on every machine.
- `document_manager.organize_documents` filed any file matching no rule
  into the *last rule's* folder instead of the default — and it moves
  files, so that was silent and irreversible.

Then, while writing the test suite that should have existed from the
start, it caught one more that I had not found by reading the code:
notes took their ID from a second-resolution timestamp, so two notes
created in the same second got the same ID and **the second silently
overwrote the first.** Data loss, in the tool whose one job is not
losing what you wrote down. The clipboard server had already been fixed
for this exact bug; notes never got the same fix.

What changed, so this is checkable rather than another claim:

- The `--test` flag is gone. There is a real `pytest` suite that calls
  every tool and asserts on output, including write-then-read-back for
  everything stateful and a `json.dumps()` check on every response.
- A startup test launches each server as a subprocess and speaks
  JSON-RPC to it. That is the test that would have caught all of this,
  and the one the old structural check could not perform by design.
- CI runs the suite on Linux, macOS and Windows across Python 3.10–3.13.
- `organize_documents` now previews by default and needs an explicit
  `dry_run=False` before it moves anything.
- `requirements.txt` was unpinned at `mcp>=1.0.0`, and mcp 2.0 removed
  `mcp.server.fastmcp` entirely — so by the end, a fresh
  `pip install -r requirements.txt` failed at import before any of the
  above could even be reached. Now pinned, and migrated to `MCPServer`.

The lesson I actually take from this is narrower than "test your code."
It is that I wrote a verification standard, believed I was applying it,
and did not notice that my check tested the one property that could not
fail. A test that cannot fail is worse than no test, because it spends
your attention and returns false confidence. That is what the banner and
the tool-count snippet both were.

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

*Verified by `tests/test_system_info.py`: every tool is called and its
output asserted against real values — a non-empty partition list with a
positive `total`, real interface names with addresses, elapsed uptime —
and every response is checked for JSON-serializability.* Needs `psutil`.

### `clipboard` — 12 tools

Your **real** OS clipboard, plus a searchable history that persists across
restarts. Read and write the clipboard, save entries under labels, search
history, merge multiple clips, clean up whitespace, convert formats.

> "Save that to my clipboard history as 'api-notes', then find the clip I
> saved about the database schema."

*Verified by `tests/test_clipboard.py`: history is written, re-read after
a fresh module load, searched, deleted and cleared. The system-clipboard
round-trip runs where a clipboard exists and skips on headless machines
rather than pretending to pass.* Uses `pbcopy`/`pbpaste` on macOS,
PowerShell (`Get-Clipboard`/`Set-Clipboard`) on Windows, `xclip`/`xsel`
on Linux. No dependencies beyond `mcp`.

**Note:** this one was previously fake — it returned the string
`"Sample clipboard text"` for every read. It has been rewritten.

### `notes` — 9 tools

Persistent notes with tags, search, and export. Create, retrieve, list,
tag, search, delete, import, and export.

> "Make a note of these three decisions and tag it 'architecture'."

*Verified by `tests/test_notes.py`: notes are created, re-read in a
separate call, listed, searched, tagged and exported — with the tag and
export assertions checking what came back off disk, not what the
response echoed.* No dependencies beyond `mcp`.

### `document_manager` — 6 tools

File management: metadata inspection, bulk organization by rules,
archiving, listing with filters.

> "Show me how you'd organize ~/Downloads by file type."

**`organize_documents` moves files, so it previews by default.** It
reports the moves it would make and changes nothing until you pass
`dry_run=False`.

*Verified by `tests/test_document_manager.py`: real metadata on real
files, archives that exist and are non-empty, a rule matrix asserting
that a file matching no rule lands in the default category, and a check
that a dry run leaves the filesystem untouched.* No dependencies beyond
`mcp`.

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
      "args": ["/absolute/path/to/business-mcp-servers/servers/document_manager.py"]
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

Servers that persist data write under `~/.local/share/business-mcp/`.

| Server | Location | Override with |
|---|---|---|
| `clipboard` | `clipboard_history.json` | `CLIPBOARD_HISTORY_PATH` |
| `notes` | `notes/` | `NOTES_STORE_PATH` |

`document_manager` has no store of its own — it operates on the paths you
give it, and writes a `<filename>.meta.json` sidecar next to a document
when you attach tags. `system_info` is read-only.

Until 2026-08-15 this section claimed both servers wrote under
`~/.local/share/business-mcp/` and "never to a hardcoded path". That was
true of `clipboard` and false of `notes`, which used a bare relative
`notes_store` resolved against the process working directory — chosen by
whatever launched the server, and easily this repo. It now matches the
table.

Nothing leaves your machine. No telemetry, no network calls, no analytics.

---

## Verify it yourself

Don't take my word for it — that's the entire point.

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite calls every tool and asserts on real output. It never asserts
on `success` alone, because `success: True` is exactly what a fabricated
tool returns.

**Check that the servers actually start**, which is the failure this repo
shipped with:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' \
  | python servers/notes.py
```

You should get a JSON-RPC result. If you get a human-readable banner, or
nothing, the server cannot talk to any MCP client — regardless of how
many tools it registers.

**The check that actually matters for any server, including ones you
didn't write** — call a tool and look at the output. For anything
stateful, *write then read back*:

```python
m.create_note(title="test", content="hello")
m.list_notes()      # must contain what you just wrote
```

If step 2 comes back empty, the server isn't persisting.

A counting check — importing the modules and totalling registered tools —
is worth running, but do not mistake it for evidence. This repo used one
as its headline verification, and it reported a healthy `41 tools` across
4 servers every day that not one of those servers could start.

---

## Requirements

Python 3.10+. `mcp` for all servers, plus `psutil` for `system_info`.
The other three use nothing beyond `mcp` and the standard library.

`mcp` is pinned to `>=2.0,<3`. These servers use `MCPServer` from
`mcp.server.mcpserver`; mcp 1.x shipped the same API as `FastMCP` under
`mcp.server.fastmcp`, which 2.0 removed. If you are on mcp 1.x, upgrade.

Linux users: `clipboard` needs `xclip` or `xsel` installed. macOS and
Windows work out of the box.

---

## Contributing

Bug reports welcome — especially **"this tool returns success but doesn't
do the thing."** That's the failure mode I care most about. If you open a
PR, please say how you tested it.

## License

MIT — see [LICENSE](LICENSE).
