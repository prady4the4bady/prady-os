"""Neila marketplace surface (v4.50).

Subpackages:

- :mod:`neila.marketplace.clawhub` — read-only HTTP client to the
  ClawHub registry (``https://clawhub.ai/api/v1``).
- :mod:`neila.marketplace.fetcher` — staging download + verify.
- :mod:`neila.marketplace.adapter` — translate OpenClaw frontmatter
  into the Neila ``SKILL.md`` shape.
- :mod:`neila.marketplace.provenance` — durable provenance records
  under ``data/state/skills/<name>/clawhub.json``.
- :mod:`neila.marketplace.install` — orchestration pipeline that
  ties fetch + adapter + skill_review together.

Plugins (Node/TypeScript packages with ``openclaw.plugin.json``) are
intentionally NOT supported. The marketplace UI filters them out at
search time and the install pipeline refuses them with a clear error.
"""

import neila.marketplace.neilahub as NEILAhub  # noqa: F401 — re-export for marketplace_api
