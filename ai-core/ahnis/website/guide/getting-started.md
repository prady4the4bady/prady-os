# Getting Started

## Installation

Install AHNIS from PyPI:

```bash
pip install AHNIS
```

::: danger Security Warning
The domain `AHNIS.tech` is a **brand-squatting site** not affiliated with this project. It is known to run ad-redirects and potential malware. The official AHNIS distribution is only available via this [GitHub repository](https://github.com/AHNIS/AHNIS) and [PyPI](https://pypi.org/project/AHNIS/). Never install binaries or scripts from unofficial domains.
:::

### Requirements

- Python 3.9+
- `chromadb>=0.5.0` (installed automatically)
- `pyyaml>=6.0` (installed automatically)

No API key required for the core local workflow. After installation, the main storage and retrieval path runs locally.

### From Source

```bash
git clone https://github.com/AHNIS/AHNIS.git
cd AHNIS
pip install -e ".[dev]"
```

## Quick Start

Three steps: **init**, **mine**, **search**.

### 1. Initialize Your Palace

`AHNIS init` requires a project directory to scan. Pass a path,
or `.` to use the current directory.

```bash
AHNIS init ~/projects/myapp
# or, from inside the project:
AHNIS init .
```

This scans your project directory and:

- Detects people and projects from file content
- Creates rooms from your folder structure
- Ensures the `~/.AHNIS/` config directory exists

### 2. Mine Your Data

```bash
# Mine project files (code, docs, notes)
AHNIS mine ~/projects/myapp

# Mine conversation exports (Claude, ChatGPT, Slack)
AHNIS mine ~/chats/ --mode convos

# Mine with auto-classification into memory types
AHNIS mine ~/chats/ --mode convos --extract general
```

Two mining modes plus one extraction strategy:
- **projects** — code and docs, auto-detected rooms
- **convos** — conversation exports, chunked by exchange pair
- **general extraction** — an `--extract general` option for conversation mining that classifies content into decisions, preferences, milestones, problems, and emotional context

### 3. Search

```bash
AHNIS search "why did we switch to GraphQL"
```

That gives you a working local memory index.

## What Happens Next

After the one-time setup, you don't run AHNIS commands manually. Your AI uses it for you through [MCP integration](/guide/mcp-integration) or a [Claude Code plugin](/guide/claude-code).

Ask your AI anything:

> *"What did we decide about auth last month?"*

It calls `AHNIS_search` automatically, gets verbatim results, and answers you. You never type `AHNIS search` again.

## Next Steps

- [Mining Your Data](/guide/mining) — deep dive into mining modes
- [MCP Integration](/guide/mcp-integration) — connect to Claude, ChatGPT, Cursor, Gemini
- [The Palace](/concepts/the-palace) — understand wings, rooms, halls, and tunnels
