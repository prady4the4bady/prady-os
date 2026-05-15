# AHNIS Claude Code Plugin

A Claude Code plugin that gives your AI a persistent memory system. Mine projects and conversations into a searchable palace backed by ChromaDB, with 19 MCP tools, auto-save hooks, and 5 guided skills.

## Prerequisites

- Python 3.9+

## Installation

### Claude Code Marketplace

```bash
claude plugin marketplace add AHNIS/AHNIS
claude plugin install --scope user AHNIS
```

### Local Clone

```bash
claude plugin add /path/to/AHNIS
```

## Post-Install Setup

After installing the plugin, run the init command to complete setup (pip install, MCP configuration, etc.):

```
/AHNIS:init
```

## Available Slash Commands

| Command | Description |
|---------|-------------|
| `/AHNIS:help` | Show available tools, skills, and architecture |
| `/AHNIS:init` | Set up AHNIS -- install, configure MCP, onboard |
| `/AHNIS:search` | Search your memories across the palace |
| `/AHNIS:mine` | Mine projects and conversations into the palace |
| `/AHNIS:status` | Show palace overview -- wings, rooms, drawer counts |

## Hooks

AHNIS registers two hooks that run automatically:

- **Stop** -- Saves conversation context every 15 messages.
- **PreCompact** -- Preserves important memories before context compaction.

Set the `MEMPAL_DIR` environment variable to a directory path to automatically run `AHNIS mine` on that directory during each save trigger.

## MCP Server

The plugin automatically configures a local MCP server with 19 tools for storing, searching, and managing memories. No manual MCP setup is required -- `/AHNIS:init` handles everything.

## Full Documentation

See the main [README](../README.md) for complete documentation, architecture details, and advanced usage.
