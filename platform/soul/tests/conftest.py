"""conftest.py for platform/soul tests"""
import sys
from pathlib import Path

# Make platform/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
