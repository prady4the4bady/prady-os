from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx

from sensor_reader import HardwareSnapshot

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AlertRule:
    condition: Callable[[HardwareSnapshot], bool]
    severity: str
    component: str
    message_template: str


@dataclass
class Alert:
    alert_id: str
    severity: str
    component: str
    message: str
    first_seen: str
    last_seen: str
    count: int
    resolved: bool = False


class AlertEngine:
    RULES: list[AlertRule] = [
        AlertRule(lambda s: s.cpu.temp_c is not None and s.cpu.temp_c > 85, 'critical', 'cpu', 'CPU temperature is {cpu_temp}°C — thermal throttling risk. Check cooling system.'),
        AlertRule(lambda s: s.cpu.temp_c is not None and 75 < s.cpu.temp_c <= 85, 'warning', 'cpu', 'CPU temperature is {cpu_temp}°C — running warm. Consider improving airflow.'),
        AlertRule(lambda s: s.memory.pressure == 'high', 'warning', 'memory', 'Memory pressure is high — only {mem_available_mb}MB available. Close unused applications.'),
        AlertRule(lambda s: any(d.smart_status == 'failing' for d in s.disks), 'critical', 'disk', 'Disk {disk_device} is reporting SMART failures ({reallocated} reallocated sectors). Back up your data immediately.'),
        AlertRule(lambda s: any(d.smart_status == 'warning' for d in s.disks), 'warning', 'disk', 'Disk {disk_device} has reallocated sectors. Monitor closely and back up data.'),
        AlertRule(lambda s: any(d.pct > 90 for d in s.disks), 'warning', 'disk', 'Disk {disk_device} is {disk_pct}% full. Free up space to avoid issues.'),
        AlertRule(lambda s: s.battery.present and s.battery.pct is not None and s.battery.pct < 10 and s.battery.status == 'discharging', 'critical', 'battery', 'Battery critically low at {battery_pct}%. Connect power immediately.'),
        AlertRule(lambda s: s.battery.present and s.battery.pct is not None and s.battery.pct < 20 and s.battery.status == 'discharging', 'warning', 'battery', 'Battery low at {battery_pct}%. Consider connecting power.'),
        AlertRule(lambda s: s.anomaly_detected, 'warning', 'system', 'Unusual hardware behaviour detected. Anomaly score: {anomaly_score:.2f}. Check Hardware dashboard for details.'),
        AlertRule(lambda s: s.gpu.present and s.gpu.temp_c is not None and s.gpu.temp_c > 90, 'critical', 'gpu', 'GPU temperature is {gpu_temp}°C — critical. Check GPU cooling.'),
    ]

    def __init__(self, notify_url: str, audit_url: str):
        self.notify_url = notify_url
        self.audit_url = audit_url
        self._active_alerts: dict[str, Alert] = {}

    def evaluate(self, snapshot: HardwareSnapshot) -> list[Alert]:
        new_alerts: list[Alert] = []
        now = _now()
        for rule in self.RULES:
            if not rule.condition(snapshot):
                continue
            key = f'{rule.severity}:{rule.component}'
            if key in self._active_alerts and not self._active_alerts[key].resolved:
                a = self._active_alerts[key]
                a.count += 1
                a.last_seen = now
                continue

            alert = Alert(
                alert_id=str(uuid.uuid4()),
                severity=rule.severity,
                component=rule.component,
                message=self.format_message(rule, snapshot),
                first_seen=now,
                last_seen=now,
                count=1,
                resolved=False,
            )
            self._active_alerts[key] = alert
            new_alerts.append(alert)

        return new_alerts

    def format_message(self, rule: AlertRule, snapshot: HardwareSnapshot) -> str:
        failing_disk = next((d for d in snapshot.disks if d.smart_status in ('failing', 'warning')), None)
        full_disk = next((d for d in snapshot.disks if d.pct > 90), None)
        return rule.message_template.format(
            cpu_temp=round(snapshot.cpu.temp_c or 0, 1),
            mem_available_mb=snapshot.memory.available_mb,
            disk_device=failing_disk.device if failing_disk else (full_disk.device if full_disk else 'unknown'),
            reallocated=failing_disk.reallocated_sectors if failing_disk else 0,
            disk_pct=round(full_disk.pct if full_disk else 0, 1),
            battery_pct=round(snapshot.battery.pct or 0, 1),
            anomaly_score=snapshot.anomaly_score,
            gpu_temp=round(snapshot.gpu.temp_c or 0, 1),
        )

    async def post_to_notify(self, alert: Alert) -> None:
        payload = {
            'type': 'hardware_alert',
            'severity': alert.severity,
            'title': f'Hardware: {alert.component}',
            'body': alert.message,
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(f'{self.notify_url}/notify', json=payload)
        except Exception as exc:
            logger.warning('notify post failed: %s', exc)

    async def post_to_audit(self, alert: Alert) -> None:
        payload = {
            'event': 'hardware_alert',
            'component': alert.component,
            'severity': alert.severity,
            'message': alert.message,
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(f'{self.audit_url}/audit/events', json=payload)
        except Exception as exc:
            logger.warning('audit post failed: %s', exc)

    def get_active_alerts(self) -> list[Alert]:
        return [a for a in self._active_alerts.values() if not a.resolved]

    def dismiss(self, alert_id: str) -> bool:
        for alert in self._active_alerts.values():
            if alert.alert_id == alert_id:
                alert.resolved = True
                return True
        return False
