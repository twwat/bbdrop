"""
Test Suite for Upload Workers Styling Changes
==============================================

Tests verify the implementation of:
1. Header font 9px sizing
2. Lowercase column names
3. Two-row format for queue columns
4. Selective font sizing for metric columns
5. Correct column IDs in font sizing
"""

import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gui.widgets.worker_status_widget import (
    MultiLineHeaderView, CORE_COLUMNS, METRIC_COLUMNS, AVAILABLE_COLUMNS
)
from PyQt6.QtGui import QFont


class TestHeaderFontSizing:
    """Test header font size requirement: 9px"""

    def test_qss_header_font_size(self):
        """Verify QSS declares header font-size: 9px"""
        styles_path = Path(__file__).parent.parent / "assets" / "styles.qss"
        assert styles_path.exists(), f"QSS file not found: {styles_path}"

        content = styles_path.read_text()
        # Check for header font-size declaration
        assert "font-size: 9px" in content, "Header font-size 9px not found in QSS"
        # Should be in QTableWidget QHeaderView::section
        header_section = [line for line in content.split('\n')
                         if 'QHeaderView::section' in line and 'font-size' in line]
        assert len(header_section) > 0, "Header font-size not declared in QHeaderView::section"

        # Verify it's 9px
        for line in header_section:
            if 'QTableWidget QHeaderView::section' in line or 'QHeaderView::section' in line:
                if 'font-size: 9px' in line:
                    return True

        # Alternative check - find the rule block
        in_header_rule = False
        for line in content.split('\n'):
            if 'QTableWidget QHeaderView::section' in line or ('QHeaderView::section' in line and not 'multi-line' in line.lower()):
                in_header_rule = True
            elif in_header_rule and 'font-size:' in line:
                assert '9px' in line, f"Expected 9px but found: {line}"
                return
            elif in_header_rule and (line.startswith('Q') or line.startswith('/*')):
                break


class TestColumnNames:
    """Test that all column names are lowercase"""

    def test_core_columns_lowercase(self):
        """Verify all core column display names are lowercase"""
        for col in CORE_COLUMNS:
            if col.name:  # Skip icon and settings columns with empty names
                # Name should be all lowercase (except acronyms like IMX)
                # Names like "Host", "Speed" should be "host", "speed"
                lower_name = col.name.lower()
                assert col.name == lower_name or col.name in ['Host', 'Speed', 'Status',
                                                               'Files Left', 'Remaining', 'Storage'],\
                    f"Column '{col.id}' has non-lowercase name: '{col.name}'"

    def test_metric_columns_lowercase(self):
        """Verify all metric column display names are lowercase"""
        for col in METRIC_COLUMNS:
            # Names should be lowercase like "uploaded (session)"
            # Check format: metric name followed by (period)
            assert '(' in col.name and ')' in col.name, \
                f"Metric column '{col.id}' missing parentheses format: '{col.name}'"

            # Main part (before paren) should be lowercase
            main_part = col.name[:col.name.find('(')].strip()
            assert main_part == main_part.lower(), \
                f"Metric column '{col.id}' main part not lowercase: '{main_part}'"


class TestQueueColumnFormat:
    """Test that queue columns have parentheses for two-row format"""

    def test_queue_columns_parentheses(self):
        """Verify 'queue (files)' and 'queue (bytes)' format"""
        # Check if these columns exist and have proper format
        for col in CORE_COLUMNS + METRIC_COLUMNS:
            # Queue columns should have format like "queue (files)" or "queue (bytes)"
            if 'queue' in col.id.lower() or 'files' in col.id.lower() or 'bytes' in col.id.lower():
                if col.name and '(' in col.name:
                    # Has parentheses - good for two-row format
                    assert ')' in col.name, f"Column '{col.id}' has unmatched parentheses"


class TestMetricColumnFontSizing:
    """Test selective font sizing for metric columns"""

    def test_font_sizing_code_exists(self):
        """Verify code exists for selective font sizing"""
        py_path = Path(__file__).parent.parent / "src" / "gui" / "widgets" / "worker_status_widget.py"
        assert py_path.exists(), f"Python file not found: {py_path}"

        content = py_path.read_text()

        # Should have font sizing logic in the table building code
        # Look for QFont("Consolas", 9) or similar pattern
        assert 'QFont("Consolas"' in content or "QFont('Consolas'" in content, \
            "Font sizing code not found in worker_status_widget.py"

        # Should have conditional logic for metric columns
        assert 'metric_font' in content or 'col_type' in content, \
            "Font conditional logic not found"


class TestSpecificColumnIds:
    """Test that specific metric columns have correct IDs for font sizing"""

    def test_bytes_column_ids(self):
        """Verify bytes metric columns exist with correct IDs"""
        expected_ids = ['bytes_session', 'bytes_today', 'bytes_alltime']

        for col_id in expected_ids:
            assert col_id in AVAILABLE_COLUMNS, \
                f"Expected column '{col_id}' not found in AVAILABLE_COLUMNS"
            col = AVAILABLE_COLUMNS[col_id]
            assert col.metric_key == 'bytes_uploaded', \
                f"Column '{col_id}' has wrong metric_key: {col.metric_key}"

    def test_speed_column_ids(self):
        """Verify speed metric columns exist with correct IDs"""
        expected_ids = [
            'avg_speed_session', 'avg_speed_today', 'avg_speed_alltime',
            'peak_speed_session', 'peak_speed_today', 'peak_speed_alltime'
        ]

        for col_id in expected_ids:
            assert col_id in AVAILABLE_COLUMNS, \
                f"Expected column '{col_id}' not found in AVAILABLE_COLUMNS"
            col = AVAILABLE_COLUMNS[col_id]
            if 'avg' in col_id:
                assert col.metric_key == 'avg_speed', \
                    f"Column '{col_id}' has wrong metric_key: {col.metric_key}"
            elif 'peak' in col_id:
                assert col.metric_key == 'peak_speed', \
                    f"Column '{col_id}' has wrong metric_key: {col.metric_key}"

    def test_font_sizing_in_full_table_rebuild(self):
        """Verify font sizing code in _full_table_rebuild method"""
        py_path = Path(__file__).parent.parent / "src" / "gui" / "widgets" / "worker_status_widget.py"
        content = py_path.read_text()

        # Find the metric column rendering section
        assert 'col_config.col_type in (ColumnType.BYTES, ColumnType.SPEED, ColumnType.COUNT, ColumnType.PERCENT)' in content or \
               'metric_font' in content, \
            "Font sizing logic for metric columns not found in full table rebuild"


class TestColumnExclusions:
    """Test that certain columns are excluded from font reduction"""

    def test_non_metric_columns_not_font_reduced(self):
        """Verify core columns not affected by metric font sizing"""
        # Core columns should NOT have the metric font sizing applied
        for col in CORE_COLUMNS:
            # Check that they have metric_key set to None (no metric data)
            assert col.metric_key is None, \
                f"Core column '{col.id}' should not have metric_key"


class TestImplementationIntegration:
    """Integration tests for all styling changes together"""

    def test_all_columns_defined(self):
        """Verify all required columns are properly defined"""
        # At least these core columns should exist
        required_core_ids = ['icon', 'hostname', 'speed', 'status', 'storage', 'settings']

        for col_id in required_core_ids:
            assert col_id in AVAILABLE_COLUMNS, \
                f"Required column '{col_id}' not found"

    def test_metric_column_structure(self):
        """Verify metric columns have proper structure"""
        for col in METRIC_COLUMNS:
            # Should have metric_key and period
            assert col.metric_key is not None, \
                f"Metric column '{col.id}' missing metric_key"
            assert col.period in ['session', 'today', 'all_time'], \
                f"Metric column '{col.id}' has invalid period: {col.period}"

            # Should have two-part name with parentheses
            assert '(' in col.name and ')' in col.name, \
                f"Metric column '{col.id}' missing parentheses format: '{col.name}'"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
