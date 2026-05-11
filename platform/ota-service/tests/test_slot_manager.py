from __future__ import annotations

from pathlib import Path

from slot_manager import SlotManager


class TestSlotManager:
    def _manager(self, tmp_path: Path) -> SlotManager:
        db = tmp_path / "slot_state.db"
        grubenv = tmp_path / "grubenv"
        return SlotManager(db, grubenv)

    def test_initial_state_defaults(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        state = manager.get_state()
        assert state["active_slot"] == "a"
        assert state["boot_fail_count"] == 0

    def test_switch_slot_toggles(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        manager.set_standby_version("1.0.1")
        state = manager.switch_slot()
        assert state["active_slot"] == "b"

    def test_rollback_after_switch_returns_to_a(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        manager.set_standby_version("1.0.1")
        manager.switch_slot()
        rolled = manager.rollback()
        assert rolled["active_slot"] == "a"

    def test_record_boot_health_false_three_times_rolls_back(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        manager.set_standby_version("1.0.1")
        manager.switch_slot()

        manager.record_boot_health(False)
        manager.record_boot_health(False)
        result = manager.record_boot_health(False)

        assert result["rolled_back"] is True
        assert result["active_slot"] == "a"

    def test_record_boot_health_true_resets_fail_count(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        manager.record_boot_health(False)
        result = manager.record_boot_health(True)
        assert result["boot_fail_count"] == 0

    def test_get_state_returns_full_dict(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        state = manager.get_state()
        for key in ("active_slot", "standby_slot", "active_version", "state", "update_history"):
            assert key in state

    def test_grubenv_written_on_switch(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        manager.set_standby_version("1.0.1")
        manager.switch_slot()
        grubenv = tmp_path / "grubenv"
        content = grubenv.read_text(encoding="utf-8")
        assert "next_entry=kryos_slot_b" in content

    def test_update_history_grows_after_switches(self, tmp_path: Path):
        manager = self._manager(tmp_path)
        before = len(manager.get_state()["update_history"])
        manager.set_standby_version("1.0.1")
        manager.switch_slot()
        manager.rollback()
        after = len(manager.get_state()["update_history"])
        assert after > before
