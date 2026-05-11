from __future__ import annotations

from alert_engine import Alert


import pytest


@pytest.mark.asyncio
async def test_init_creates_tables(db):
    cur = await db._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hardware_snapshots'")
    assert await cur.fetchone() is not None
    cur = await db._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'")
    assert await cur.fetchone() is not None


@pytest.mark.asyncio
async def test_store_snapshot_returns_id(db, mock_snapshot):
    sid = await db.store_snapshot(mock_snapshot)
    assert isinstance(sid, str)
    assert len(sid) > 10


@pytest.mark.asyncio
async def test_get_history_cpu_metric(db, mock_snapshot):
    await db.store_snapshot(mock_snapshot)
    points = await db.get_history('cpu_temp', hours=24)
    assert isinstance(points, list)
    assert points


@pytest.mark.asyncio
async def test_get_history_hours_filter(db, mock_snapshot):
    await db.store_snapshot(mock_snapshot)
    points = await db.get_history('memory_used', hours=1)
    assert isinstance(points, list)


@pytest.mark.asyncio
async def test_get_snapshots_since(db, mock_snapshot):
    await db.store_snapshot(mock_snapshot)
    rows = await db.get_snapshots_since(hours=24)
    assert isinstance(rows, list)
    assert rows


@pytest.mark.asyncio
async def test_store_alert_persists(db):
    alert = Alert(alert_id='a1', severity='warning', component='cpu', message='x', first_seen='t1', last_seen='t1', count=1)
    await db.store_alert(alert)
    active = await db.get_active_alerts()
    assert any(a['alert_id'] == 'a1' for a in active)


@pytest.mark.asyncio
async def test_dismiss_alert_sets_resolved(db):
    alert = Alert(alert_id='a2', severity='warning', component='cpu', message='x', first_seen='t1', last_seen='t1', count=1)
    await db.store_alert(alert)
    ok = await db.dismiss_alert('a2')
    assert ok is True


@pytest.mark.asyncio
async def test_get_active_alerts_excludes_resolved(db):
    alert = Alert(alert_id='a3', severity='warning', component='cpu', message='x', first_seen='t1', last_seen='t1', count=1)
    await db.store_alert(alert)
    await db.dismiss_alert('a3')
    active = await db.get_active_alerts()
    assert all(a['alert_id'] != 'a3' for a in active)


@pytest.mark.asyncio
async def test_get_alert_count(db):
    cnt = await db.get_alert_count()
    assert isinstance(cnt, int)


@pytest.mark.asyncio
async def test_history_disk_pct(db, mock_snapshot):
    mock_snapshot.disks[0].pct = 88.0
    await db.store_snapshot(mock_snapshot)
    points = await db.get_history('disk_pct', hours=24)
    assert points and points[0]['value'] >= 0
