# MCP Integration — Claude Code

## Setup

Run the MCP server:

```bash
AHNIS-mcp
```

Or add it to Claude Code:

```bash
claude mcp add AHNIS -- AHNIS-mcp
```

## Available Tools

The server exposes the full AHNIS MCP toolset. Common entry points include:

- **AHNIS_status** — palace stats (wings, rooms, drawer counts)
- **AHNIS_search** — semantic search across all memories
- **AHNIS_list_wings** — list all projects in the palace

## Usage in Claude Code

Once configured, Claude Code can search your memories directly during conversations.
