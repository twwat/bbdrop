"""Centralized disk space monitoring with adaptive polling and tiered alerts.

Monitors two paths (data dir for DB/artifacts, temp dir for archives),
deduplicates by mount point, and emits signals when free space crosses
configurable thresholds.
"""

import os
import shutil

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.utils.logger import log


class DiskSpaceMonitor(QObject):
    """Monitors disk space on data and temp directories with adaptive polling."""

    # Emitted when tier changes: "ok", "warning", "critical", "emergency"
    tier_changed = pyqtSignal(str)
    # Emitted on every poll: (data_free_bytes, temp_free_bytes)
    space_updated = pyqtSignal(int, int)

    # Adaptive polling intervals (ms)
    _INTERVAL_COMFORTABLE = 60_000  # > 2x warning
    _INTERVAL_APPROACHING = 15_000  # > warning
    _INTERVAL_DANGER = 5_000        # > critical
    _INTERVAL_EMERGENCY = 2_000     # <= critical

    def __init__(
        self,
        data_dir: str,
        temp_dir: str,
        warning_mb: int = 2048,
        critical_mb: int = 512,
        emergency_mb: int = 100,
        parent=None,
    ):
        super().__init__(parent)
        self._data_dir = data_dir
        self._temp_dir = temp_dir
        self._warning_bytes = warning_mb * 1024 * 1024
        self._critical_bytes = critical_mb * 1024 * 1024
        self._emergency_bytes = emergency_mb * 1024 * 1024

        self._current_tier = "ok"
        self._current_interval_ms = self._INTERVAL_COMFORTABLE
        self._data_free = 0
        self._temp_free = 0

        # Check if both paths are on the same device
        self._same_device = self._check_same_device()

        # Reserve file path (alongside the DB)
        self._reserve_path = os.path.join(data_dir, "disk_reserve.bin")
        self._reserve_size = 20 * 1024 * 1024  # 20 MB

        # Polling timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    def start(self):
        """Start monitoring. Call after moving to main thread if needed."""
        self._ensure_reserve_file()
        self._poll()  # Initial check
        self._timer.start(self._current_interval_ms)

    def stop(self):
        """Stop monitoring."""
        self._timer.stop()

    @property
    def current_tier(self) -> str:
        return self._current_tier

    @property
    def data_free(self) -> int:
        return self._data_free

    @property
    def temp_free(self) -> int:
        return self._temp_free

    def can_start_upload(self) -> bool:
        """Return False if space is critically low (critical or emergency)."""
        return self._current_tier in ("ok", "warning")

    def can_create_archive(self, estimated_bytes: int) -> bool:
        """Return False if temp dir doesn't have room for the archive + margin."""
        return self._temp_free > estimated_bytes + self._critical_bytes

    def request_emergency_space(self) -> int:
        """Delete the reserve file to free space for DB flushes. Returns bytes freed."""
        if os.path.exists(self._reserve_path):
            try:
                size = os.path.getsize(self._reserve_path)
                os.remove(self._reserve_path)
                log(f"Deleted disk reserve file, freed {size // (1024 * 1024)}MB",
                    level="warning", category="disk")
                return size
            except OSError as e:
                log(f"Failed to delete reserve file: {e}",
                    level="error", category="disk")
        return 0

    def update_thresholds(self, warning_mb: int, critical_mb: int, emergency_mb: int):
        """Update thresholds from settings. Takes effect on next poll."""
        self._warning_bytes = warning_mb * 1024 * 1024
        self._critical_bytes = critical_mb * 1024 * 1024
        self._emergency_bytes = emergency_mb * 1024 * 1024

    def update_paths(self, data_dir: str, temp_dir: str):
        """Update monitored paths (e.g. when central storage changes)."""
        self._data_dir = data_dir
        self._temp_dir = temp_dir
        self._same_device = self._check_same_device()
        self._reserve_path = os.path.join(data_dir, "disk_reserve.bin")

    def _poll(self):
        """Check disk space and update tier."""
        try:
            data_usage = shutil.disk_usage(self._data_dir)
            self._data_free = data_usage.free

            if self._same_device:
                self._temp_free = self._data_free
            else:
                temp_usage = shutil.disk_usage(self._temp_dir)
                self._temp_free = temp_usage.free
        except OSError as e:
            log(f"Disk space check failed: {e}", level="warning", category="disk")
            return

        # Tier is determined by the lower free space
        min_free = min(self._data_free, self._temp_free)
        new_tier = self._calculate_tier(min_free)

        # Emit space update every poll
        self.space_updated.emit(self._data_free, self._temp_free)

        # Handle tier transitions
        if new_tier != self._current_tier:
            old_tier = self._current_tier
            self._current_tier = new_tier
            log(f"Disk space tier: {old_tier} -> {new_tier} "
                f"(data: {self._data_free // (1024*1024)}MB, "
                f"temp: {self._temp_free // (1024*1024)}MB)",
                level="warning" if new_tier != "ok" else "info",
                category="disk")
            self.tier_changed.emit(new_tier)

            # Emergency action: delete reserve
            if new_tier == "emergency":
                self.request_emergency_space()

        # Adjust polling interval
        new_interval = self._calculate_interval(min_free)
        if new_interval != self._current_interval_ms:
            self._current_interval_ms = new_interval
            self._timer.setInterval(new_interval)

    def _calculate_tier(self, free_bytes: int) -> str:
        if free_bytes < self._emergency_bytes:
            return "emergency"
        elif free_bytes < self._critical_bytes:
            return "critical"
        elif free_bytes < self._warning_bytes:
            return "warning"
        return "ok"

    def _calculate_interval(self, free_bytes: int) -> int:
        if free_bytes > self._warning_bytes * 2:
            return self._INTERVAL_COMFORTABLE
        elif free_bytes > self._warning_bytes:
            return self._INTERVAL_APPROACHING
        elif free_bytes > self._critical_bytes:
            return self._INTERVAL_DANGER
        return self._INTERVAL_EMERGENCY

    def _check_same_device(self) -> bool:
        """Return True if data_dir and temp_dir are on the same filesystem."""
        try:
            return os.stat(self._data_dir).st_dev == os.stat(self._temp_dir).st_dev
        except OSError:
            return False  # Can't tell — monitor both

    def _ensure_reserve_file(self):
        """Create the reserve file if it doesn't exist."""
        if os.path.exists(self._reserve_path):
            return
        try:
            with open(self._reserve_path, 'wb') as f:
                f.write(b'\x00' * self._reserve_size)
            log(f"Created {self._reserve_size // (1024*1024)}MB disk reserve at {self._reserve_path}",
                level="info", category="disk")
        except OSError as e:
            log(f"Could not create disk reserve file: {e}",
                level="warning", category="disk")
