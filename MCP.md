# MCP server

`mcp_server.py` exposes Parent Check's two scam-analysis tools over the
[Model Context Protocol](https://modelcontextprotocol.io), so any MCP client can
call the same tools the in-app Gemini agent uses:

| Tool | What it does | Needs |
|---|---|---|
| `check_phone_numbers(text, lang)` | Extract + classify phone numbers (mobile / premium-rate / international / helpline) | nothing (pure function) |
| `query_knowledge_base(text, lang)` | Vector-similarity search over the scam-case corpus | DB + `GEMINI_API_KEY` |

Both publish a JSON schema (from the type hints), validate input at the boundary
(non-empty, ≤5000 chars, `lang ∈ {en, zh}`), and audit-log each call with the
input **length only** — never its contents.

## Run

```bash
pip install -r requirements.txt
python mcp_server.py          # stdio transport
```

## Register with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "parent-check": {
      "command": "python",
      "args": ["/absolute/path/to/parent-check/mcp_server.py"],
      "env": { "GEMINI_API_KEY": "..." }
    }
  }
}
```

`check_phone_numbers` works with no env. `query_knowledge_base` returns a clear
error object until the database and `GEMINI_API_KEY` are configured, so a client
can degrade gracefully.
