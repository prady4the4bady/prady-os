> [!CAUTION]
> **Scam alert.** The only official sources for AHNIS are this
> [GitHub repository](https://github.com/AHNIS/AHNIS), the
> [PyPI package](https://pypi.org/project/AHNIS/), and the docs site at
> **[AHNISofficial.com](https://AHNISofficial.com)**. Any other
> domain — including `AHNIS.tech` — is an impostor and may distribute
> malware. Details and timeline: [docs/HISTORY.md](docs/HISTORY.md).

<div align="center">

<img src="assets/AHNIS_logo.png" alt="AHNIS" width="240">

# AHNIS

Local-first AI memory. Verbatim storage, pluggable backend, 96.6% R@5 raw on LongMemEval — zero API calls.

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]
[![][discord-shield]][discord-link]

</div>

---

## What it is

AHNIS stores your conversation history as verbatim text and retrieves
it with semantic search. It does not summarize, extract, or paraphrase.
The index is structured — people and projects become *wings*, topics
become *rooms*, and original content lives in *drawers* — so searches
can be scoped rather than run against a flat corpus.

The retrieval layer is pluggable. The current default is ChromaDB; the
interface is defined in [`AHNIS/backends/base.py`](AHNIS/backends/base.py)
and alternative backends can be dropped in without touching the rest of
the system.

Nothing leaves your machine unless you opt in.

Architecture, concepts, and mining flows:
[AHNISofficial.com/concepts/the-palace](https://AHNISofficial.com/concepts/the-palace.html).

---

## Install

```bash
pip install AHNIS
AHNIS init ~/projects/myapp
```

## Quickstart

```bash
# Mine content into the palace
AHNIS mine ~/projects/myapp                    # project files
AHNIS mine ~/.claude/projects/ --mode convos   # Claude Code sessions (scope with --wing per project)

# Search
AHNIS search "why did we switch to GraphQL"

# Load context for a new session
AHNIS wake-up
```

For Claude Code, Gemini CLI, MCP-compatible tools, and local models, see
[AHNISofficial.com/guide/getting-started](https://AHNISofficial.com/guide/getting-started.html).

---

## Benchmarks

All numbers below are reproducible from this repository with the commands
in [`benchmarks/BENCHMARKS.md`](benchmarks/BENCHMARKS.md). Full
per-question result files are committed under `benchmarks/results_*`.

**LongMemEval — retrieval recall (R@5, 500 questions):**

| Mode | R@5 | LLM required |
|---|---|---|
| Raw (semantic search, no heuristics, no LLM) | **96.6%** | None |
| Hybrid v4, held-out 450q (tuned on 50 dev, not seen during training) | **98.4%** | None |
| Hybrid v4 + LLM rerank (full 500) | ≥99% | Any capable model |

The raw 96.6% requires no API key, no cloud, and no LLM at any stage. The
hybrid pipeline adds keyword boosting, temporal-proximity boosting, and
preference-pattern extraction; the held-out 98.4% is the honest
generalisable figure.

The rerank pipeline promotes the best candidate out of the top-20
retrieved sessions using an LLM reader. It works with any reasonably
capable model — we have reproduced it with Claude Haiku, Claude Sonnet,
and minimax-m2.7 via Ollama Cloud (no Anthropic dependency). The gap
between raw and reranked is model-agnostic; we do not headline a "100%"
number because the last 0.6% was reached by inspecting specific wrong
answers, which `benchmarks/BENCHMARKS.md` flags as teaching to the test.

**Other benchmarks (full results in [`benchmarks/BENCHMARKS.md`](benchmarks/BENCHMARKS.md)):**

| Benchmark | Metric | Score | Notes |
|---|---|---|---|
| LoCoMo (session, top-10, no rerank) | R@10 | 60.3% | 1,986 questions |
| LoCoMo (hybrid v5, top-10, no rerank) | R@10 | 88.9% | Same set |
| ConvoMem (all categories, 250 items) | Avg recall | 92.9% | 50 per category |
| MemBench (ACL 2025, 8,500 items) | R@5 | 80.3% | All categories |

We deliberately do not include a side-by-side comparison against Mem0,
Mastra, Hindsight, Supermemory, or Zep. Those projects publish different
metrics on different splits, and placing retrieval recall next to
end-to-end QA accuracy is not an honest comparison. See each project's
own research page for their published numbers.

**Reproducing every result:**

```bash
git clone https://github.com/AHNIS/AHNIS.git
cd AHNIS
pip install -e ".[dev]"
# see benchmarks/README.md for dataset download commands
python benchmarks/longmemeval_bench.py /path/to/longmemeval_s_cleaned.json
```

---

## Knowledge graph

AHNIS includes a temporal entity-relationship graph with validity
windows — add, query, invalidate, timeline — backed by local SQLite.
Usage and tool reference:
[AHNISofficial.com/concepts/knowledge-graph](https://AHNISofficial.com/concepts/knowledge-graph.html).

## MCP server

29 MCP tools cover palace reads/writes, knowledge-graph operations,
cross-wing navigation, drawer management, and agent diaries. Installation
and the full tool list:
[AHNISofficial.com/reference/mcp-tools](https://AHNISofficial.com/reference/mcp-tools.html).

## Agents

Each specialist agent gets its own wing and diary in the palace.
Discoverable at runtime via `AHNIS_list_agents` — no bloat in your
system prompt:
[AHNISofficial.com/concepts/agents](https://AHNISofficial.com/concepts/agents.html).

## Auto-save hooks

Two Claude Code hooks save periodically and before context compression:
[AHNISofficial.com/guide/hooks](https://AHNISofficial.com/guide/hooks.html).

For per-message recall on top of the file-level chunks the hooks produce,
run `AHNIS sweep <transcript-dir>` periodically — it stores one
verbatim drawer per user/assistant message, idempotent and resume-safe.

---

## Requirements

- Python 3.9+
- A vector-store backend (ChromaDB by default)
- ~300 MB disk for the default embedding model

No API key is required for the core benchmark path.

## Docs

- Getting started → [AHNISofficial.com/guide/getting-started](https://AHNISofficial.com/guide/getting-started.html)
- CLI reference → [AHNISofficial.com/reference/cli](https://AHNISofficial.com/reference/cli.html)
- Python API → [AHNISofficial.com/reference/python-api](https://AHNISofficial.com/reference/python-api.html)
- Full benchmark methodology → [benchmarks/BENCHMARKS.md](benchmarks/BENCHMARKS.md)
- Release notes → [CHANGELOG.md](CHANGELOG.md)
- Corrections and public notices → [docs/HISTORY.md](docs/HISTORY.md)

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

<!-- Link Definitions -->
[version-shield]: https://img.shields.io/badge/version-3.3.3-4dc9f6?style=flat-square&labelColor=0a0e14
[release-link]: https://github.com/AHNIS/AHNIS/releases
[python-shield]: https://img.shields.io/badge/python-3.9+-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/AHNIS/AHNIS/blob/main/LICENSE
[discord-shield]: https://img.shields.io/badge/discord-join-5865F2?style=flat-square&labelColor=0a0e14&logo=discord&logoColor=5865F2
[discord-link]: https://discord.com/invite/ycTQQCu6kn
