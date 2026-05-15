# Gemini CLI

AHNIS works natively with [Gemini CLI](https://github.com/google/gemini-cli), which handles the MCP server and save hooks automatically.

## Prerequisites

- Python 3.9+
- Gemini CLI installed and configured

## Installation

```bash
# Clone the repository
git clone https://github.com/AHNIS/AHNIS.git
cd AHNIS

# Create a virtual environment
python3 -m venv .venv

# Install dependencies
.venv/bin/pip install -e .
```

## Initialize the Palace

```bash
.venv/bin/python3 -m AHNIS init .
```

### Identity and Project Configuration (Optional)

You can optionally create or edit:

- **`~/.AHNIS/identity.txt`** — plain text describing your role and focus
- **`./AHNIS.yaml`** — per-project AHNIS configuration created by `AHNIS init`
- **`./entities.json`** — per-project entity mappings used by AAAK compression

## Connect to Gemini CLI

Register AHNIS as an MCP server:

```bash
gemini mcp add --scope user AHNIS \
  -- /absolute/path/to/AHNIS/.venv/bin/python -m AHNIS.mcp_server
```

::: warning
Use the **absolute path** to the Python binary so the server starts from any
working directory. The `--` separator prevents Gemini from parsing
`-m AHNIS.mcp_server` as its own flags.
:::

## Enable Auto-Saving

Add a `PreCompress` hook to `~/.gemini/settings.json`:

```json
{
  "hooks": {
    "PreCompress": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "/absolute/path/to/AHNIS/hooks/mempal_precompact_hook.sh"
          }
        ]
      }
    ]
  }
}
```

Make sure the hook scripts are executable:
```bash
chmod +x hooks/*.sh
```

## Usage

Once connected, Gemini CLI will automatically:
- Start the AHNIS server on launch
- Use `AHNIS_search` to find relevant past discussions
- Use the `PreCompress` hook to save memories before context compression

### Manual Mining

Mine existing code or docs:
```bash
.venv/bin/python3 -m AHNIS mine /path/to/your/project
```

### Verification

In a Gemini CLI session:
- `/mcp list` — verify `AHNIS` is `CONNECTED`
- `/hooks panel` — verify the `PreCompress` hook is active
