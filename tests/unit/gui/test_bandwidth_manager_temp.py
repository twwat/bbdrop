#!/usr/bin/env python3
"""
Comprehensive pytest-qt tests for BandwidthManager and BandwidthSource.

This test suite provides thorough coverage including:
- Asymmetric EMA smoothing (alpha_up=0.6 fast rise, alpha_down=0.15 slow decay)
- Multi-source bandwidth aggregation (IMX.to, file hosts, link checker)
- PyQt6 signal emission and reception with qtbot
- Thread safety with QMutex
- QSettings persistence of smoothing parameters
- Peak tracking and session management
- Host lifecycle (creation, completion, cleanup)
- Edge cases and error handling

Uses pytest-qt fixtures for proper Qt integration testing.
"""





# Test file content continues...
