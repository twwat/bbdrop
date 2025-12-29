#!/usr/bin/env python3
"""
Diagnostic test to find the exact blocking point in main_window.py import.
Tests incremental imports to isolate where the hang occurs.
"""

import sys
import time
sys.path.insert(0, '.')

def timed_step(description, func):
    """Execute a function and report timing."""
    print(f"\n{description}...", flush=True)
    start = time.time()
    try:
        result = func()
        elapsed = (time.time() - start) * 1000
        print(f"✓ {description} completed in {elapsed:.1f}ms", flush=True)
        return result
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"✗ {description} FAILED after {elapsed:.1f}ms: {e}", flush=True)
        raise

print("=" * 60)
print("DIAGNOSTIC: Incremental Import Test")
print("=" * 60)

# Step 1: Initialize MetricsStore first
timed_step("Step 1: Initialize MetricsStore", lambda: __import__('src.utils.metrics_store'))
from src.utils.metrics_store import get_metrics_store
ms = timed_step("Step 1b: Call get_metrics_store()", lambda: get_metrics_store())
print(f"  MetricsStore ready: {ms}")

# Step 2: Import PyQt6 modules that worker_status_widget needs
def import_pyqt():
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QIcon
    return Qt.AlignmentFlag.AlignLeft

alignment = timed_step("Step 2: Import PyQt6 modules", import_pyqt)
print(f"  Qt alignment: {alignment}")

# Step 3: Import ColumnConfig dataclass components
def import_dataclasses():
    from dataclasses import dataclass, field
    from typing import Optional
    from enum import Enum
    return dataclass, field

dc, f = timed_step("Step 3: Import dataclasses", import_dataclasses)

# Step 4: Create ColumnConfig with field(default_factory=lambda)
def create_column_config():
    from dataclasses import dataclass, field
    from PyQt6.QtCore import Qt
    from enum import Enum

    class ColumnType(Enum):
        TEXT = "text"

    @dataclass
    class ColumnConfig:
        id: str
        name: str
        width: int
        col_type: ColumnType
        alignment: Qt.AlignmentFlag = field(default_factory=lambda: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # Create instance - this might trigger the issue
    col = ColumnConfig('test', 'Test', 100, ColumnType.TEXT)
    return col

col = timed_step("Step 4: Create ColumnConfig with default_factory", create_column_config)
print(f"  Column created: {col.id}")

# Step 5: Create multiple ColumnConfigs in a list comprehension (like AVAILABLE_COLUMNS)
def create_column_dict():
    from dataclasses import dataclass, field
    from PyQt6.QtCore import Qt
    from enum import Enum

    class ColumnType(Enum):
        TEXT = "text"
        ICON = "icon"

    @dataclass
    class ColumnConfig:
        id: str
        name: str
        width: int
        col_type: ColumnType
        alignment: Qt.AlignmentFlag = field(default_factory=lambda: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    CORE_COLUMNS = [
        ColumnConfig('icon', '', 24, ColumnType.ICON),
        ColumnConfig('hostname', 'Host', 120, ColumnType.TEXT),
        ColumnConfig('speed', 'Speed', 90, ColumnType.TEXT),
    ]

    METRIC_COLUMNS = [
        ColumnConfig('bytes_session', 'Session', 90, ColumnType.TEXT),
        ColumnConfig('bytes_today', 'Today', 90, ColumnType.TEXT),
    ]

    # THIS IS LINE 90 in worker_status_widget.py - the suspected blocking line
    AVAILABLE_COLUMNS = {col.id: col for col in CORE_COLUMNS + METRIC_COLUMNS}

    return AVAILABLE_COLUMNS

cols = timed_step("Step 5: Create AVAILABLE_COLUMNS dict (LINE 90)", create_column_dict)
print(f"  Columns created: {list(cols.keys())}")

# Step 6: Now import worker_status_widget module
def import_worker_widget():
    from src.gui.widgets.worker_status_widget import WorkerStatusWidget
    return WorkerStatusWidget

widget_class = timed_step("Step 6: Import worker_status_widget module", import_worker_widget)
print(f"  Widget class: {widget_class.__name__}")

# Step 7: Finally import main_window (the full import)
def import_main_window():
    from src.gui.main_window import ImxUploadGUI
    return ImxUploadGUI

gui_class = timed_step("Step 7: Import main_window module", import_main_window)
print(f"  GUI class: {gui_class.__name__}")

print("\n" + "=" * 60)
print("✓ ALL IMPORTS SUCCEEDED - NO BLOCKING DETECTED")
print("=" * 60)
