"""Centralized bandwidth tracking system for BBDrop.

This module provides a unified approach to bandwidth monitoring across all upload
sources (IMX.to, file hosts, link checker). It implements asymmetric EMA smoothing
for stable, responsive bandwidth display that rises quickly and falls gradually.

Classes:
    BandwidthSource: Per-source bandwidth tracking with smoothing.
    BandwidthManager: Central coordinator for all bandwidth sources.
"""

import time
from collections import deque
from typing import Dict, Optional

from PyQt6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    QSettings,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)


class BandwidthSource:
    """Per-source bandwidth tracking with asymmetric EMA smoothing.

    Uses a rolling average combined with asymmetric exponential moving average
    (EMA) smoothing. The asymmetric approach allows the display to rise quickly
    when bandwidth increases but fall gradually when it decreases, providing
    a stable yet responsive user experience.

    Attributes:
        name: Identifier for this bandwidth source.
        active: Whether this source is currently active.
    """

    def __init__(
        self,
        name: str,
        window_size: int = 20,
        alpha_up: float = 0.6,
        alpha_down: float = 0.35,
    ) -> None:
        """Initialize a bandwidth source.

        Args:
            name: Identifier for this bandwidth source.
            window_size: Number of samples for rolling average.
            alpha_up: EMA smoothing factor for increasing values (0-1).
                Higher values = faster response to increases.
            alpha_down: EMA smoothing factor for decreasing values (0-1).
                Lower values = slower decay when bandwidth drops.
        """
        self.name = name
        self.active = True

        self._window_size = window_size
        self._alpha_up = alpha_up
        self._alpha_down = alpha_down

        self._samples: deque[float] = deque(maxlen=window_size)
        self._smoothed_kbps: float = 0.0
        self._last_update: float = time.time()
        self._peak_value: float = 0.0

    def add_sample(self, kbps: float) -> float:
        """Add a bandwidth sample and return the smoothed value.

        Applies rolling average followed by asymmetric EMA smoothing.
        The smoothing factor used depends on whether the new value is
        higher or lower than the current smoothed value.

        Args:
            kbps: Instantaneous bandwidth in KB/s.

        Returns:
            The smoothed bandwidth value in KB/s.
        """
        self._last_update = time.time()
        self._samples.append(kbps)

        # Calculate rolling average
        rolling_avg = sum(self._samples) / len(self._samples)

        # Apply asymmetric EMA
        if rolling_avg > self._smoothed_kbps:
            alpha = self._alpha_up
        else:
            alpha = self._alpha_down

        self._smoothed_kbps = alpha * rolling_avg + (1 - alpha) * self._smoothed_kbps

        # Track peak
        if self._smoothed_kbps > self._peak_value:
            self._peak_value = self._smoothed_kbps

        return self._smoothed_kbps

    def set_alpha(self, alpha_up: float, alpha_down: float) -> None:
        """Update the smoothing parameters.

        Args:
            alpha_up: New EMA factor for increasing values (0-1).
            alpha_down: New EMA factor for decreasing values (0-1).
        """
        self._alpha_up = max(0.0, min(1.0, alpha_up))
        self._alpha_down = max(0.0, min(1.0, alpha_down))

    def reset(self) -> None:
        """Clear all samples and reset smoothed value to zero."""
        self._samples.clear()
        self._smoothed_kbps = 0.0
        self._last_update = time.time()

    @property
    def smoothed_value(self) -> float:
        """Get the current smoothed bandwidth value in KB/s."""
        return self._smoothed_kbps

    @property
    def peak_value(self) -> float:
        """Get the peak bandwidth value recorded for this source."""
        return self._peak_value

    @property
    def time_since_update(self) -> float:
        """Get seconds elapsed since the last sample was added."""
        return time.time() - self._last_update


class BandwidthManager(QObject):
    """Central coordinator for all bandwidth sources.

    Manages bandwidth tracking for IMX.to uploads, file host uploads, and
    link checker operations. Provides aggregated totals and per-host tracking
    with thread-safe access and automatic cleanup of inactive sources.

    Signals:
        total_bandwidth_updated: Emitted with total KB/s (smoothed).
        host_bandwidth_updated: Emitted with host name and KB/s.
        peak_updated: Emitted when a new session peak is recorded.

    Class Attributes:
        DEFAULT_ALPHA_UP: Default smoothing factor for increases.
        DEFAULT_ALPHA_DOWN: Default smoothing factor for decreases.
        SETTINGS_KEY_ALPHA_UP: QSettings key for alpha_up value.
        SETTINGS_KEY_ALPHA_DOWN: QSettings key for alpha_down value.
    """

    # Signals
    total_bandwidth_updated = pyqtSignal(float)
    host_bandwidth_updated = pyqtSignal(str, float)
    peak_updated = pyqtSignal(float)

    # Class constants
    DEFAULT_ALPHA_UP = 0.6
    DEFAULT_ALPHA_DOWN = 0.35
    SETTINGS_KEY_ALPHA_UP = "bandwidth/alpha_up"
    SETTINGS_KEY_ALPHA_DOWN = "bandwidth/alpha_down"

    # Emit interval in milliseconds
    EMIT_INTERVAL_MS = 200

    # Cleanup delay for completed hosts in milliseconds
    HOST_CLEANUP_DELAY_MS = 5000

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize the bandwidth manager.

        Loads smoothing parameters from QSettings and creates the primary
        bandwidth sources. Starts a timer for periodic aggregation.

        Args:
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        # Load smoothing parameters from settings
        settings = QSettings("BBDropUploader", "Settings")
        self._alpha_up = settings.value(
            self.SETTINGS_KEY_ALPHA_UP,
            self.DEFAULT_ALPHA_UP,
            type=float,
        )
        self._alpha_down = settings.value(
            self.SETTINGS_KEY_ALPHA_DOWN,
            self.DEFAULT_ALPHA_DOWN,
            type=float,
        )

        # Create primary sources
        self._upload_source = BandwidthSource(
            "",
            alpha_up=self._alpha_up,
            alpha_down=self._alpha_down,
        )
        self._link_checker_source = BandwidthSource(
            "link_checker",
            alpha_up=self._alpha_up,
            alpha_down=self._alpha_down,
        )

        # File host sources (created dynamically)
        self._file_host_sources: Dict[str, BandwidthSource] = {}

        # Thread safety lock
        self._lock = QMutex()

        # Session peak tracking
        self._session_peak: float = 0.0

        # Aggregation timer
        self._emit_timer = QTimer(self)
        self._emit_timer.timeout.connect(self._emit_aggregated)
        self._emit_timer.start(self.EMIT_INTERVAL_MS)

        # Cleanup timers for hosts
        self._cleanup_timers: Dict[str, QTimer] = {}

    @pyqtSlot(float)
    def on_upload_bandwidth(self, instant_kbps: float) -> None:
        """Handle bandwidth update from IMX.to uploads.

        Args:
            instant_kbps: Instantaneous bandwidth in KB/s.
        """
        self._upload_source.active = True
        self._upload_source.add_sample(instant_kbps)

    @pyqtSlot(str, float)
    def on_file_host_bandwidth(self, host_name: str, instant_kbps: float) -> None:
        """Handle bandwidth update from a file host upload.

        Creates a new BandwidthSource if this is a new host.

        Args:
            host_name: Name of the file host.
            instant_kbps: Instantaneous bandwidth in KB/s.
        """
        locker = QMutexLocker(self._lock)

        if host_name not in self._file_host_sources:
            self._file_host_sources[host_name] = BandwidthSource(
                host_name,
                alpha_up=self._alpha_up,
                alpha_down=self._alpha_down,
            )

        source = self._file_host_sources[host_name]
        source.active = True
        smoothed = source.add_sample(instant_kbps)

        locker.unlock()

        # Emit per-host update
        self.host_bandwidth_updated.emit(host_name, smoothed)

        # Cancel any pending cleanup for this host
        if host_name in self._cleanup_timers:
            self._cleanup_timers[host_name].stop()
            del self._cleanup_timers[host_name]

    @pyqtSlot(float)
    def on_link_checker_bandwidth(self, instant_kbps: float) -> None:
        """Handle bandwidth update from link checker operations.

        Args:
            instant_kbps: Instantaneous bandwidth in KB/s.
        """
        self._link_checker_source.active = True
        self._link_checker_source.add_sample(instant_kbps)

    @pyqtSlot(str)
    def on_host_completed(self, host_name: str) -> None:
        """Mark a file host as inactive and schedule cleanup.

        The host source is marked inactive immediately but not removed
        until after a delay to allow the bandwidth display to decay
        gracefully.

        Args:
            host_name: Name of the completed file host.
        """
        locker = QMutexLocker(self._lock)

        if host_name in self._file_host_sources:
            self._file_host_sources[host_name].active = False

        locker.unlock()

        # Schedule cleanup after delay
        if host_name not in self._cleanup_timers:
            cleanup_timer = QTimer(self)
            cleanup_timer.setSingleShot(True)
            cleanup_timer.timeout.connect(lambda: self._cleanup_host(host_name))
            cleanup_timer.start(self.HOST_CLEANUP_DELAY_MS)
            self._cleanup_timers[host_name] = cleanup_timer

    def _emit_aggregated(self) -> None:
        """Aggregate all sources and emit total bandwidth signal.

        Called periodically by the emit timer. Sums bandwidth from all
        active sources and emits the total. Updates session peak if
        a new maximum is reached.
        """
        total = 0.0

        # Add IMX bandwidth
        if self._upload_source.active:
            total += self._upload_source.smoothed_value

        # Add link checker bandwidth
        if self._link_checker_source.active:
            total += self._link_checker_source.smoothed_value

        # Add file host bandwidths
        locker = QMutexLocker(self._lock)
        for source in self._file_host_sources.values():
            if source.active:
                total += source.smoothed_value
        locker.unlock()

        # Only emit if there's actual bandwidth (avoid spamming UI with zeros)
        if total > 0:
            self.total_bandwidth_updated.emit(total)

        # Track session peak
        if total > self._session_peak:
            self._session_peak = total
            self.peak_updated.emit(self._session_peak)

    def _cleanup_host(self, host_name: str) -> None:
        """Remove a file host source after its cleanup delay.

        Args:
            host_name: Name of the host to remove.
        """
        locker = QMutexLocker(self._lock)

        if host_name in self._file_host_sources:
            del self._file_host_sources[host_name]

        locker.unlock()

        # Remove the cleanup timer
        if host_name in self._cleanup_timers:
            del self._cleanup_timers[host_name]

    def get_total_bandwidth(self) -> float:
        """Get the current total bandwidth across all sources.

        Returns:
            Total bandwidth in KB/s.
        """
        total = 0.0

        if self._upload_source.active:
            total += self._upload_source.smoothed_value

        if self._link_checker_source.active:
            total += self._link_checker_source.smoothed_value

        locker = QMutexLocker(self._lock)
        for source in self._file_host_sources.values():
            if source.active:
                total += source.smoothed_value
        locker.unlock()

        return total

    def get_imx_bandwidth(self) -> float:
        """Get the current IMX.to bandwidth.

        Returns:
            IMX.to bandwidth in KB/s.
        """
        return self._upload_source.smoothed_value

    def get_file_host_bandwidth(self, host_name: str) -> float:
        """Get the current bandwidth for a specific file host.

        Args:
            host_name: Name of the file host.

        Returns:
            Host bandwidth in KB/s, or 0.0 if host not found.
        """
        locker = QMutexLocker(self._lock)

        if host_name in self._file_host_sources:
            value = self._file_host_sources[host_name].smoothed_value
        else:
            value = 0.0

        locker.unlock()
        return value

    def get_session_peak(self) -> float:
        """Get the peak bandwidth recorded this session.

        Returns:
            Session peak bandwidth in KB/s.
        """
        return self._session_peak

    def get_active_hosts(self) -> list[str]:
        """Get a list of currently active file hosts.

        Returns:
            List of active host names.
        """
        locker = QMutexLocker(self._lock)

        active = [
            name
            for name, source in self._file_host_sources.items()
            if source.active
        ]

        locker.unlock()
        return active

    def update_smoothing(self, alpha_up: float, alpha_down: float) -> None:
        """Update smoothing parameters for all sources.

        Persists the new values to QSettings.

        Args:
            alpha_up: New EMA factor for increasing values (0-1).
            alpha_down: New EMA factor for decreasing values (0-1).
        """
        self._alpha_up = max(0.0, min(1.0, alpha_up))
        self._alpha_down = max(0.0, min(1.0, alpha_down))

        # Update all sources
        self._upload_source.set_alpha(self._alpha_up, self._alpha_down)
        self._link_checker_source.set_alpha(self._alpha_up, self._alpha_down)

        locker = QMutexLocker(self._lock)
        for source in self._file_host_sources.values():
            source.set_alpha(self._alpha_up, self._alpha_down)
        locker.unlock()

        # Persist to settings
        settings = QSettings("BBDropUploader", "Settings")
        settings.setValue(self.SETTINGS_KEY_ALPHA_UP, self._alpha_up)
        settings.setValue(self.SETTINGS_KEY_ALPHA_DOWN, self._alpha_down)

    def get_smoothing_settings(self) -> tuple[float, float]:
        """Get the current smoothing parameters.

        Returns:
            Tuple of (alpha_up, alpha_down).
        """
        return (self._alpha_up, self._alpha_down)

    def stop(self) -> None:
        """Stop the aggregation timer and cleanup timers.

        Should be called before destroying the manager.
        Must be called from the main thread (timers can only be stopped
        from the thread that owns them).
        """
        from PyQt6.QtCore import QThread, QCoreApplication, QMetaObject, Qt
        
        # Check if we're on the main thread
        if QThread.currentThread() != QCoreApplication.instance().thread():
            # Schedule stop on main thread to avoid Qt warning
            QMetaObject.invokeMethod(
                self, "_stop_timers_impl",
                Qt.ConnectionType.QueuedConnection
            )
            return
        
        self._stop_timers_impl()
    
    @pyqtSlot()
    def _stop_timers_impl(self) -> None:
        """Actually stop the timers (must run on main thread)."""
        self._emit_timer.stop()

        # Stop all cleanup timers
        for timer in self._cleanup_timers.values():
            timer.stop()
        self._cleanup_timers.clear()

    def reset_session(self) -> None:
        """Reset the session peak to zero.

        Call this when starting a new upload session.
        """
        self._session_peak = 0.0

        # Also reset all sources
        self._upload_source.reset()
        self._link_checker_source.reset()

        locker = QMutexLocker(self._lock)
        for source in self._file_host_sources.values():
            source.reset()
        locker.unlock()