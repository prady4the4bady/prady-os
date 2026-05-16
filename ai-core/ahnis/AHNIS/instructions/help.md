# AHNIS

AI memory system. Store everything, find anything. Local, free, no API key.

---

## Slash Commands

| Command              | Description                    |
|----------------------|--------------------------------|
| /AHNIS:init      | Install and set up AHNIS   |
| /AHNIS:search    | Search your memories           |
| /AHNIS:mine      | Mine projects and conversations|
| /AHNIS:status    | Palace overview and stats      |
| /AHNIS:help      | This help message              |

---

## MCP Tools (19)

### Palace (read)
- AHNIS_status -- Palace status and stats
- AHNIS_list_wings -- List all wings
- AHNIS_list_rooms -- List rooms in a wing
- AHNIS_get_taxonomy -- Get the full taxonomy tree
- AHNIS_search -- Search memories by query
- AHNIS_check_duplicate -- Check if a memory already exists
- AHNIS_get_aaak_spec -- Get the AAAK specification

### Palace (write)
- AHNIS_add_drawer -- Add a new memory (drawer)
- AHNIS_delete_drawer -- Delete a memory (drawer)

### Knowledge Graph
- AHNIS_kg_query -- Query the knowledge graph
- AHNIS_kg_add -- Add a knowledge graph entry
- AHNIS_kg_invalidate -- Invalidate a knowledge graph entry
- AHNIS_kg_timeline -- View knowledge graph timeline
- AHNIS_kg_stats -- Knowledge graph statistics

### Navigation
- AHNIS_traverse -- Traverse the palace structure
- AHNIS_find_tunnels -- Find cross-wing connections
- AHNIS_graph_stats -- Graph connectivity statistics

### Agent Diary
- AHNIS_diary_write -- Write a diary entry
- AHNIS_diary_read -- Read diary entries

---

## CLI Commands

    AHNIS init <dir>                  Initialize a new palace
    AHNIS mine <dir>                  Mine a project (default mode)
    AHNIS mine <dir> --mode convos    Mine conversation exports
    AHNIS search "query"              Search your memories
    AHNIS split <dir>                 Split large transcript files
    AHNIS wake-up                     Load palace into context
    AHNIS compress                    Compress palace storage
    AHNIS status                      Show palace status
    AHNIS repair                      Rebuild vector index
    AHNIS mcp                         Show MCP setup command
    AHNIS hook run                    Run hook logic (for harness integration)
    AHNIS instructions <name>         Output skill instructions

---

## Auto-Save Hooks

- Stop hook -- Automatically saves memories every 15 messages. Counts human
  messages in the session transcript (skipping command-messages). When the
  threshold is reached, blocks the AI with a save instruction. Uses
  ~/.AHNIS/hook_state/ to track save points per session. If
  stop_hook_active is true, passes through to prevent infinite loops.

- PreCompact hook -- Emergency save before context compaction. Always blocks
  with a comprehensive save instruction because compaction means the AI is
  about to lose detailed context.

Hooks read JSON from stdin and output JSON to stdout. They can be invoked via:

    echo '{"session_id":"abc","stop_hook_active":false,"transcript_path":"..."}' | AHNIS hook run --hook stop --harness claude-code

---

## Architecture

    Wings (projects/people)
      +-- Rooms (topics)
            +-- Closets (summaries)
                  +-- Drawers (verbatim memories)

    Halls connect rooms within a wing.
    Tunnels connect rooms across wings.

The palace is stored locally using ChromaDB for vector search and SQLite for
metadata. No cloud services or API keys required.

---

## Getting Started

1. /AHNIS:init -- Set up your palace
2. /AHNIS:mine -- Mine a project or conversation
3. /AHNIS:search -- Find what you stored
