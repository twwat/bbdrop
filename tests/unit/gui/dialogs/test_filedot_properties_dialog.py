"""Unit tests for FiledotPropertiesDialog.

The dialog is pure layout + diff logic (no I/O). These tests construct
it with qtbot, drive the widgets, and assert the get_changed_fields
output for both single and multi modes.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from src.gui.dialogs.filedot_properties_dialog import FiledotPropertiesDialog


INITIAL = {
    "file_name": "Original File.zip",
    "file_descr": "Old description text",
    "file_password": "oldpw",
    "file_price": "2.50",
    "file_public": "1",
    "file_premium_only": "0",
}


def test_single_mode_populates_from_initial(qtbot):
    dlg = FiledotPropertiesDialog(initial=INITIAL, multi=False)
    qtbot.addWidget(dlg)

    assert dlg._name_edit.text() == "Original File.zip"
    assert dlg._descr_edit.toPlainText() == "Old description text"
    assert dlg._password_edit.text() == "oldpw"
    assert abs(dlg._price_spin.value() - 2.50) < 1e-6
    assert dlg._public_check.isChecked() is True
    assert dlg._premium_check.isChecked() is False


def test_single_mode_no_change_returns_empty_diff(qtbot):
    """Opening and accepting without editing returns an empty diff."""
    dlg = FiledotPropertiesDialog(initial=INITIAL, multi=False)
    qtbot.addWidget(dlg)

    assert dlg.get_changed_fields() == {}


def test_single_mode_changing_description_returns_only_descr(qtbot):
    dlg = FiledotPropertiesDialog(initial=INITIAL, multi=False)
    qtbot.addWidget(dlg)

    dlg._descr_edit.setPlainText("brand new description")

    diff = dlg.get_changed_fields()
    assert diff == {"file_descr": "brand new description"}


def test_single_mode_changing_price_and_password_returns_two_fields(qtbot):
    dlg = FiledotPropertiesDialog(initial=INITIAL, multi=False)
    qtbot.addWidget(dlg)

    dlg._price_spin.setValue(9.99)
    dlg._password_edit.setText("newpw")

    diff = dlg.get_changed_fields()
    assert diff == {"file_price": "9.99", "file_password": "newpw"}


def test_single_mode_toggling_flags_flips_0_and_1(qtbot):
    dlg = FiledotPropertiesDialog(initial=INITIAL, multi=False)
    qtbot.addWidget(dlg)

    # public was 1, unchecking should diff to "0"
    dlg._public_check.setChecked(False)
    # premium was 0, checking should diff to "1"
    dlg._premium_check.setChecked(True)

    diff = dlg.get_changed_fields()
    assert diff == {"file_public": "0", "file_premium_only": "1"}


def test_multi_mode_hides_name_row(qtbot):
    dlg = FiledotPropertiesDialog(multi=True)
    qtbot.addWidget(dlg)

    # isHidden() is True iff setVisible(False) was called, regardless of
    # whether the dialog itself has been shown yet.
    assert dlg._name_edit.isHidden() is True
    assert dlg._name_label.isHidden() is True


def test_multi_mode_checkboxes_start_partially_checked(qtbot):
    dlg = FiledotPropertiesDialog(multi=True)
    qtbot.addWidget(dlg)

    assert dlg._public_check.isTristate() is True
    assert dlg._premium_check.isTristate() is True
    assert dlg._public_check.checkState() == Qt.CheckState.PartiallyChecked
    assert dlg._premium_check.checkState() == Qt.CheckState.PartiallyChecked


def test_multi_mode_untouched_returns_empty_diff(qtbot):
    """Opening multi-mode dialog without touching anything gives empty diff."""
    dlg = FiledotPropertiesDialog(multi=True)
    qtbot.addWidget(dlg)

    assert dlg.get_changed_fields() == {}


def test_multi_mode_setting_public_flag_returns_just_public(qtbot):
    dlg = FiledotPropertiesDialog(multi=True)
    qtbot.addWidget(dlg)

    dlg._public_check.setCheckState(Qt.CheckState.Checked)

    diff = dlg.get_changed_fields()
    assert diff == {"file_public": "1"}


def test_multi_mode_setting_description_and_price(qtbot):
    dlg = FiledotPropertiesDialog(multi=True)
    qtbot.addWidget(dlg)

    dlg._descr_edit.setPlainText("batch desc")
    dlg._price_spin.setValue(4.25)

    diff = dlg.get_changed_fields()
    assert diff == {"file_descr": "batch desc", "file_price": "4.25"}


def test_multi_mode_never_emits_file_name(qtbot):
    """file_name is intentionally excluded from multi-mode diffs."""
    dlg = FiledotPropertiesDialog(multi=True)
    qtbot.addWidget(dlg)

    # Even if we hack the name field to have a value, diff should skip it
    dlg._name_edit.setText("hacked")

    diff = dlg.get_changed_fields()
    assert "file_name" not in diff


def test_multi_mode_unchecking_premium_returns_zero(qtbot):
    """Cycling a tri-state checkbox from Partial → Unchecked returns '0'."""
    dlg = FiledotPropertiesDialog(multi=True)
    qtbot.addWidget(dlg)

    dlg._premium_check.setCheckState(Qt.CheckState.Unchecked)

    diff = dlg.get_changed_fields()
    assert diff == {"file_premium_only": "0"}
