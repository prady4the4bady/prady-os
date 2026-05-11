"""Wake Word Detector – OpenWakeWord wrapper."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

try:
    from openwakeword.model import Model as OWWModel
except ImportError:
    OWWModel = None  # type: ignore


class WakeWordDetector:
    """OpenWakeWord wake word detection."""

    def __init__(
        self,
        wake_word: str = "hey_kryos",
        threshold: float = 0.5,
        models_dir: str | None = None,
    ):
        self.wake_word = wake_word
        self.threshold = threshold
        self.models_dir = Path(models_dir or Path.home() / ".kryos" / "models" / "wake_word")
        self._model = None
        self._running = False
        self._thread = None
        self._callback = None

    def start(self, callback: Callable[[str], None]) -> None:
        """Start wake word detection in background thread.

        Args:
            callback: Async function to call on detection: callback(keyword: str)
        """
        if self._running:
            logger.warning("Wake word detector already running")
            return

        self._callback = callback
        self._running = True

        try:
            if OWWModel is None:
                logger.warning("OpenWakeWord not installed, wake word detection disabled")
                return

            # Load model
            model_path = self.models_dir / f"{self.wake_word}.tflite"
            self.models_dir.mkdir(parents=True, exist_ok=True)

            try:
                self._model = OWWModel(
                    wakeword_models={self.wake_word: str(model_path)},
                )
                logger.info(f"Loaded wake word model: {self.wake_word}")
            except Exception as e:
                logger.warning(f"Failed to load OpenWakeWord model: {e}")
                return

            # Start background thread
            self._thread = threading.Thread(target=self._detection_loop, daemon=True)
            self._thread.start()
        except Exception as e:
            logger.error(f"Failed to start wake word detector: {e}")
            self._running = False

    def stop(self) -> None:
        """Stop wake word detection."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def is_running(self) -> bool:
        """Check if detection is running."""
        return self._running

    def _detection_loop(self) -> None:
        """Background detection loop (stub for testing)."""
        while self._running:
            try:
                # In tests, we'll mock this
                # In production, would read from audio device and call model.predict()
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"Detection loop error: {e}")
                break
