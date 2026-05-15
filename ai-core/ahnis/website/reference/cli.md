# CLI Commands

All commands accept `--palace <path>` to override the default palace location.

## `AHNIS init`

Scan a project directory for people, projects, and rooms, and set up the palace.

```bash
AHNIS init <dir>                 # <dir> is required
AHNIS init <dir> --yes           # non-interactive mode
AHNIS init ~/projects/myapp      # example
AHNIS init .                     # initialize from the current directory
```

| Option  | Description                                                                  |
|---------|------------------------------------------------------------------------------|
| `<dir>` | **Required.** Project directory to scan. Pass `.` for the current directory. |
| `--yes` | Auto-accept all detected entities                                            |

What it does:

1. Scans `<dir>` for people and projects in file content
2. Detects rooms from `<dir>`'s folder structure
3. Saves detected entities to `<dir>/entities.json`
4. Ensures the global `~/.AHNIS/` config directory exists

Running `AHNIS init` with no argument will exit with
`error: the following arguments are required: dir`.

## `AHNIS mine`

Mine files into the palace.

```bash
AHNIS mine <dir>
AHNIS mine <dir> --mode convos
AHNIS mine <dir> --mode convos --extract general
AHNIS mine <dir> --wing myapp
```

| Option | Default | Description |
|--------|---------|-------------|
| `<dir>` | — | Directory to mine |
| `--mode` | `projects` | `projects` for code/docs, `convos` for chat exports |
| `--wing` | directory name | Wing name override |
| `--agent` | `AHNIS` | Agent name tag |
| `--limit` | `0` (all) | Max files to process |
| `--dry-run` | — | Preview without filing |
| `--extract` | `exchange` | `exchange` or `general` (for convos mode) |
| `--no-gitignore` | — | Don't respect .gitignore |
| `--include-ignored` | — | Always scan these paths even if ignored |

## `AHNIS search`

Find anything by semantic search.

```bash
AHNIS search "query"
AHNIS search "query" --wing myapp
AHNIS search "query" --wing myapp --room auth
AHNIS search "query" --results 10
```

| Option | Default | Description |
|--------|---------|-------------|
| `"query"` | — | What to search for |
| `--wing` | all | Filter by wing |
| `--room` | all | Filter by room |
| `--results` | `5` | Number of results |

## `AHNIS split`

Split concatenated transcript mega-files into per-session files.

```bash
AHNIS split <dir>
AHNIS split <dir> --dry-run
AHNIS split <dir> --min-sessions 3
AHNIS split <dir> --output-dir ~/split-output/
```

| Option | Default | Description |
|--------|---------|-------------|
| `<dir>` | — | Directory with transcript files |
| `--output-dir` | same dir | Write split files here |
| `--dry-run` | — | Preview without writing |
| `--min-sessions` | `2` | Only split files with N+ sessions |

## `AHNIS wake-up`

Show L0 + L1 wake-up context (~600–900 tokens).

```bash
AHNIS wake-up
AHNIS wake-up --wing driftwood
```

| Option | Description |
|--------|-------------|
| `--wing` | Project-specific wake-up |

## `AHNIS compress`

Compress drawers using AAAK Dialect.

```bash
AHNIS compress --wing myapp
AHNIS compress --wing myapp --dry-run
AHNIS compress --config entities.json
```

| Option | Description |
|--------|-------------|
| `--wing` | Wing to compress (default: all) |
| `--dry-run` | Preview without storing |
| `--config` | Entity config JSON file |

## `AHNIS status`

Show what's been filed — drawer count, wing/room breakdown.

```bash
AHNIS status
```

## `AHNIS repair`

Rebuild palace vector index from stored data. Fixes segfaults after database corruption.

```bash
AHNIS repair
```

Creates a backup at `<palace_path>.backup` before rebuilding.

## `AHNIS mcp`

Helper command that outputs setup syntax (like `claude mcp add...`) to connect AHNIS to your AI client, automatically handling paths.

```bash
AHNIS mcp
AHNIS mcp --palace ~/.custom-palace
```

## `AHNIS hook`

Run hook logic for Claude Code / Codex integration.

```bash
AHNIS hook run --hook stop --harness claude-code
AHNIS hook run --hook precompact --harness claude-code
AHNIS hook run --hook session-start --harness codex
```

| Option | Values | Description |
|--------|--------|-------------|
| `--hook` | `session-start`, `stop`, `precompact` | Hook name |
| `--harness` | `claude-code`, `codex` | Harness type |

## `AHNIS instructions`

Output skill instructions to stdout.

```bash
AHNIS instructions init
AHNIS instructions search
AHNIS instructions mine
AHNIS instructions help
AHNIS instructions status
```
