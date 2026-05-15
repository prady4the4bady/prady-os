---
name: AHNIS
description: AHNIS — mine projects and conversations into a searchable memory palace. Use when asked about AHNIS, memory palace, mining memories, searching memories, or palace setup.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# AHNIS

A searchable memory palace for AI — mine projects and conversations, then search them semantically.

## Prerequisites

Ensure `AHNIS` is installed:

```bash
AHNIS --version
```

If not installed:

```bash
pip install AHNIS
```

## Usage

AHNIS provides dynamic instructions via the CLI. To get instructions for any operation:

```bash
AHNIS instructions <command>
```

Where `<command>` is one of: `help`, `init`, `mine`, `search`, `status`.

Run the appropriate instructions command, then follow the returned instructions step by step.
