# Mining Your Data

AHNIS ingests your data by **mining** — scanning files and filing their content as verbatim drawers in the palace.

## Mining Modes

### Projects Mode (default)

Scans code, docs, and notes. Respects `.gitignore` by default.

```bash
AHNIS mine ~/projects/myapp
```

Each file becomes a drawer, tagged with a wing (project name) and room (topic). Rooms are auto-detected from your folder structure during `AHNIS init`.

Options:
```bash
# Override wing name
AHNIS mine ~/projects/myapp --wing myapp

# Ignore .gitignore rules
AHNIS mine ~/projects/myapp --no-gitignore

# Include specific ignored paths
AHNIS mine ~/projects/myapp --include-ignored dist,build

# Limit number of files
AHNIS mine ~/projects/myapp --limit 100

# Preview without filing
AHNIS mine ~/projects/myapp --dry-run
```

### Conversations Mode

Indexes conversation exports from Claude, ChatGPT, Slack, and other tools. Chunks by exchange pair (human + assistant turns).

```bash
AHNIS mine ~/chats/ --mode convos
```

Supports five chat formats automatically:
- Claude JSON exports
- ChatGPT exports
- Slack exports
- Markdown conversations
- Plain text transcripts

### General Extraction

Auto-classifies conversation content into five memory types:

```bash
AHNIS mine ~/chats/ --mode convos --extract general
```

Memory types:
- **Decisions** — choices made, options rejected
- **Preferences** — habits, likes, opinions
- **Milestones** — sessions completed, goals reached
- **Problems** — bugs, blockers, issues encountered
- **Emotional context** — reactions, concerns, excitement

## Splitting Mega-Files

Some transcript exports concatenate multiple sessions into one huge file. Split them first:

```bash
# Preview what would be split
AHNIS split ~/chats/ --dry-run

# Split files with 2+ sessions (default)
AHNIS split ~/chats/

# Only split files with 3+ sessions
AHNIS split ~/chats/ --min-sessions 3

# Output to a different directory
AHNIS split ~/chats/ --output-dir ~/chats-split/
```

::: tip
Always run `AHNIS split` before mining conversation files. It's a no-op if files don't need splitting.
:::

## Multi-Project Setup

Mine each project into its own wing:

```bash
AHNIS mine ~/chats/orion/  --mode convos --wing orion
AHNIS mine ~/chats/nova/   --mode convos --wing nova
AHNIS mine ~/chats/helios/ --mode convos --wing helios
```

Six months later:
```bash
# Project-specific search
AHNIS search "database decision" --wing orion

# Cross-project search
AHNIS search "rate limiting approach"
# → finds your approach in Orion AND Nova, shows the differences
```

## Team Usage

Mine Slack exports and AI conversations for team history:

```bash
AHNIS mine ~/exports/slack/ --mode convos --wing driftwood
AHNIS mine ~/.claude/projects/ --mode convos
```

Then search across people and projects:
```bash
AHNIS search "Soren sprint" --wing driftwood
# → 14 closets: OAuth refactor, dark mode, component library migration
```

## Agent Tag

Every drawer is tagged with the agent that filed it:

```bash
# Default agent name
AHNIS mine ~/data/ --agent AHNIS

# Custom agent name
AHNIS mine ~/data/ --agent reviewer
```

This is used by [Specialist Agents](/concepts/agents) to partition memories.
