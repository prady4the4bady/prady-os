from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DATA = ROOT / "tests" / ".tmp"
TEST_DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("AUTH_DB_PATH", str(TEST_DATA / "auth.db"))
os.environ.setdefault("JWT_PRIVATE_KEY_PATH", str(TEST_DATA / "jwt-private.pem"))
os.environ.setdefault("JWT_PUBLIC_KEY_PATH", str(TEST_DATA / "jwt-public.pem"))
