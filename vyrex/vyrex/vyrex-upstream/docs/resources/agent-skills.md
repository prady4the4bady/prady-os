---
title:
  page: "Vyrex Agent Skills for Your AI Coding Assistant"
  nav: "Agent Skills"
description:
  main: "Vyrex ships agent skills that let AI coding assistants guide you through installation, configuration, and operation."
  agent: "Describes the agent skills shipped with Vyrex and how to access them by cloning the repository. Use when users ask about AI agent support, coding assistant integration, or the .agents/skills/ directory."
keywords: ["vyrex agent skills", "ai coding assistant", "cursor", "claude code", "copilot"]
topics: ["generative_ai", "ai_agents"]
tags: ["openclaw", "openshell", "agent_skills", "vyrex"]
content:
  type: concept
  difficulty: technical_beginner
  audience: ["developer", "engineer"]
status: published
---

<!--
  SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# Vyrex Agent Skills for Your AI Coding Assistant

Vyrex ships agent skills that are generated directly from this documentation.
Each skill is a converted version of one or more doc pages, structured so AI coding assistants can consume it as context.
This means you can interact with the full Vyrex documentation as skills inside your agent chat session, instead of reading the docs separately.

Ask your assistant a question about Vyrex and it responds with the same guidance found in these docs, adapted to your current situation.
Skills cover installation, inference configuration, network policy management, monitoring, deployment, security, workspace management, and the CLI reference.

:::{note}
If you are a contributor and have cloned the full Vyrex repository, the full set of skills including contributor and maintainer skills are already available at the project root.
Open the `Vyrex` directory in your coding assistant and the skills load automatically.
This page is for users who installed Vyrex with the installer and do not have a local clone.
:::

## Get the Skills

Fetch only the skills from the Vyrex repository without downloading the full source tree.

```console
$ git clone --filter=blob:none --no-checkout https://github.com/NVIDIA/Vyrex.git
$ cd Vyrex
$ git sparse-checkout set --no-cone '/.agents/skills/vyrex-user-*/**' '/.agents/skills/vyrex-skills-guide/**' '/.claude/**' '/AGENTS.md' '/CLAUDE.md'
$ git checkout
```

Open the `Vyrex` directory in your AI coding assistant.
The assistant discovers the skills in `.agents/skills/` and uses them to answer Vyrex questions with project-specific guidance.

You can keep the skills inside the cloned directory or copy `.agents/skills/` to a global location (such as `~/.cursor/skills/` or `~/.claude/skills/`) so they are available across all your projects.
The choice depends on whether you want Vyrex skills scoped to one workspace or accessible everywhere.

## Update the Skills

The sparse checkout filter is saved, so `git pull` fetches only updated skills without downloading the full source tree.
Run `git pull` after each Vyrex release to pick up new and updated skills.

## Available Skills

The following user skills ship with Vyrex.

```{include} ../../.agents/skills/vyrex-skills-guide/SKILL.md
:start-after: <!-- user-skills-table:begin -->
:end-before: <!-- user-skills-table:end -->
```

## Example Questions and Triggered Skills

After opening the cloned repository in your coding assistant, ask a Vyrex question in natural language.
The assistant matches your question to the relevant skill and follows the guidance it contains.

Examples of questions your assistant can answer with these skills:

| Question | Skill triggered |
|----------|-----------------|
| "How do I install Vyrex?" | `vyrex-user-get-started` |
| "Switch my inference provider to Ollama." | `vyrex-user-configure-inference` |
| "A network request was blocked. How do I approve it?" | `vyrex-user-manage-policy` |
| "Show me the sandbox logs." | `vyrex-user-monitor-sandbox` |
| "How do I deploy Vyrex to a remote GPU?" | `vyrex-user-deploy-remote` |
| "What security controls can I configure?" | `vyrex-user-configure-security` |
| "Back up my agent workspace files." | `vyrex-user-workspace` |
| "What CLI commands are available?" | `vyrex-user-reference` |

You can also reference a skill directly by name if you know which one you need.

## AI Coding Assistants that You Can Use with Vyrex Skills

The Vyrex agent skills follow the [Agent Skills best practices](https://agentskills.io/skill-creation/best-practices) and the [Claude Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).
The following table shows how each AI coding assistant can use the Vyrex skills.

| Assistant | Skill discovery |
|-----------|----------------|
| Cursor | Reads `AGENTS.md` at the project root, which references `.agents/skills/`. |
| Claude Code | Follows the `.claude/skills/` symlink, which points to `.agents/skills/`. |
| Other assistants | Point the assistant to `.agents/skills/` if it supports project-level skill loading. |
