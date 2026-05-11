from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from sensor_reader import HardwareSnapshot

MODEL_PATH = '/data/hardware_intel/anomaly_model.pkl'
SCALER_PATH = '/data/hardware_intel/anomaly_scaler.pkl'


@dataclass
class TrainingResult:
    success: bool
    samples: int
    features: int
    message: str = ''


@dataclass
class AnomalyResult:
    score: float
    anomaly_detected: bool


FEATURE_NAMES = [
    'cpu_temp_c',
    'cpu_usage_pct',
    'mem_used_pct',
    'disk_pct_max',
    'battery_pct',
    'net_bytes_recv_ps_total',
]


class AnomalyDetector:
    def __init__(self, model_path: str = MODEL_PATH, scaler_path: str = SCALER_PATH):
        self._model: IsolationForest | None = None
        self._scaler: StandardScaler | None = None
        self._trained = False
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.contamination = 0.05
        self.last_trained_ts: str | None = None
        self.samples_trained: int = 0

    def _extract_features(self, snapshot: HardwareSnapshot) -> np.ndarray:
        cpu_temp = snapshot.cpu.temp_c or 40.0
        cpu_usage = snapshot.cpu.usage_pct or 0.0
        mem_used_pct = (snapshot.memory.used_mb / max(snapshot.memory.total_mb, 1)) * 100.0
        disk_pct_max = max((d.pct for d in snapshot.disks), default=0.0)
        battery_pct = snapshot.battery.pct if snapshot.battery.present and snapshot.battery.pct is not None else 100.0
        net_recv = sum(n.bytes_recv_ps for n in snapshot.network)
        return np.array([[cpu_temp, cpu_usage, mem_used_pct, disk_pct_max, battery_pct, net_recv]], dtype=np.float64)

    def train(self, snapshots: list[HardwareSnapshot]) -> TrainingResult:
        if len(snapshots) < 10:
            return TrainingResult(success=False, samples=len(snapshots), features=6, message='Need at least 10 snapshots to train')

        X = np.vstack([self._extract_features(s) for s in snapshots])
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)
        self._model = IsolationForest(contamination=self.contamination, n_estimators=100, random_state=42)
        self._model.fit(X_scaled)
        self._trained = True
        Path(self.model_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, self.model_path)
        joblib.dump(self._scaler, self.scaler_path)
        self.samples_trained = len(snapshots)
        from datetime import datetime, timezone
        self.last_trained_ts = datetime.now(timezone.utc).isoformat()
        return TrainingResult(success=True, samples=len(snapshots), features=6)

    def predict(self, snapshot: HardwareSnapshot) -> AnomalyResult:
        if not self._trained:
            self.load()
        if not self._trained or self._model is None or self._scaler is None:
            return AnomalyResult(score=0.5, anomaly_detected=False)

        X = self._extract_features(snapshot)
        X_scaled = self._scaler.transform(X)
        raw_score = float(self._model.score_samples(X_scaled)[0])
        normalized = min(1.0, max(0.0, (raw_score + 0.5) / 0.5))
        return AnomalyResult(score=normalized, anomaly_detected=normalized < 0.3)

    def load(self) -> bool:
        try:
            self._model = joblib.load(self.model_path)
            self._scaler = joblib.load(self.scaler_path)
            self._trained = True
            return True
        except (FileNotFoundError, Exception):
            return False
