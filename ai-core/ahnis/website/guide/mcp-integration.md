# MCP Integration

AHNIS provides 29 tools through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), giving any MCP-compatible AI full read/write access to your palace.

## Setup

### Setup Helper

AHNIS includes a setup helper that prints the exact configuration commands for your environment:

```bash
AHNIS mcp
```

### Manual Connection

```bash
claude mcp add AHNIS -- python -m AHNIS.mcp_server
```

### With Custom Palace Path

```bash
claude mcp add AHNIS -- python -m AHNIS.mcp_server --palace /path/to/palace
```

Now your AI has all 29 tools available. Ask it anything:

> *"What did we decide about auth last month?"*

Claude calls `AHNIS_search` automatically, gets verbatim results, and answers you.

## Compatible Tools

AHNIS works with any tool that supports MCP:

- **Claude Code** — native via plugin or manual MCP
- **OpenClaw** — via official skill, see [OpenClaw Skill](/guide/openclaw)
- **ChatGPT** — via MCP bridge
- **Cursor** — native MCP support
- **Gemini CLI** — see [Gemini CLI guide](/guide/gemini-cli)

## Memory Protocol

When the AI first calls `AHNIS_status`, it receives the **Memory Protocol** — a behavior guide that teaches it to:

1. **On wake-up**: Call `AHNIS_status` to load the palace overview
2. **Before responding** about any person, project, or past event: search first, never guess
3. **If unsure**: Say "let me check" and query the palace
4. **After each session**: Write diary entries to record what happened
5. **When facts change**: Invalidate old facts, add new ones

This protocol is what turns storage into memory — the AI knows to verify before speaking.

## Tool Overview

### Palace (read)

| Tool | What |
|------|------|
| `AHNIS_status` | Palace overview + AAAK spec + memory protocol |
| `AHNIS_list_wings` | Wings with counts |
| `AHNIS_list_rooms` | Rooms within a wing |
| `AHNIS_get_taxonomy` | Full wing → room → count tree |
| `AHNIS_search` | Semantic search with wing/room filters |
| `AHNIS_check_duplicate` | Check before filing |
| `AHNIS_get_aaak_spec` | AAAK dialect reference |

### Drawers (read)

| Tool | What |
|------|------|
| `AHNIS_get_drawer` | Fetch a single drawer by ID |
| `AHNIS_list_drawers` | List drawers with pagination |

### Palace (write)

| Tool | What |
|------|------|
| `AHNIS_add_drawer` | File verbatim content |
| `AHNIS_update_drawer` | Update drawer content or metadata |
| `AHNIS_delete_drawer` | Remove by ID |

### Knowledge Graph

| Tool | What |
|------|------|
| `AHNIS_kg_query` | Entity relationships with time filtering |
| `AHNIS_kg_add` | Add facts |
| `AHNIS_kg_invalidate` | Mark facts as ended |
| `AHNIS_kg_timeline` | Chronological entity story |
| `AHNIS_kg_stats` | Graph overview |

### Navigation

| Tool | What |
|------|------|
| `AHNIS_traverse` | Walk the graph from a room across wings |
| `AHNIS_find_tunnels` | Find rooms bridging two wings |
| `AHNIS_graph_stats` | Graph connectivity overview |

### Tunnels

| Tool | What |
|------|------|
| `AHNIS_create_tunnel` | Create an explicit cross-wing tunnel |
| `AHNIS_list_tunnels` | List all explicit tunnels |
| `AHNIS_delete_tunnel` | Delete an explicit tunnel |
| `AHNIS_follow_tunnels` | Follow tunnels out from a room |

### Agent Diary

| Tool | What |
|------|------|
| `AHNIS_diary_write` | Write AAAK diary entry |
| `AHNIS_diary_read` | Read recent diary entries |

### System

| Tool | What |
|------|------|
| `AHNIS_hook_settings` | Get or set hook behavior |
| `AHNIS_memories_filed_away` | Check whether the last checkpoint was saved |
| `AHNIS_reconnect` | Force reconnect to the database |

For detailed schemas and parameters, see [MCP Tools Reference](/reference/mcp-tools).
