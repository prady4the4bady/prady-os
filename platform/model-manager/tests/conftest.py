"""Pytest configuration for model-manager tests."""
import sys
from pathlib import Path

# Add model-manager root to Python path so prady_models can be imported
_model_manager_root = Path(__file__).parents[1]
if str(_model_manager_root) not in sys.path:
    sys.path.insert(0, str(_model_manager_root))
