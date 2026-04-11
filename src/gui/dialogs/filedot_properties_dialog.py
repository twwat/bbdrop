"""Properties dialog for editing Filedot file attributes.

Pure layout + diff logic — no I/O. The controller is responsible for
reading scraped values (single-file mode) and for posting the diff
through the file manager worker.

Single-file mode (multi=False): pre-populate all widgets from `initial`,
return only fields whose widget value differs from initial.

Multi-file mode (multi=True): hide the name row, start checkboxes in
PartiallyChecked, start text fields empty. Return only fields the user
actually touched — PartiallyChecked and empty-string count as "leave
unchanged" and are excluded from the diff.
"""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)


class FiledotPropertiesDialog(QDialog):
    """Edit file_name, file_descr, file_password, file_price, and the
    file_public / file_premium_only flags for one or many Filedot files.
    """

    def __init__(
        self,
        initial: Optional[Dict[str, str]] = None,
        multi: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Properties (multiple files)" if multi else "File Properties"
        )
        self.setMinimumWidth(420)

        self._multi = multi
        self._initial: Dict[str, str] = dict(initial or {})

        self._setup_ui()
        if not multi:
            self._populate_from_initial()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)
        layout.addLayout(form)

        if self._multi:
            header = QLabel(
                "Only fields you change will be applied to the selected "
                "files. Untouched fields keep their current values."
            )
            header.setWordWrap(True)
            layout.insertWidget(0, header)

        self._name_edit = QLineEdit()
        self._name_label = QLabel("Name:")
        form.addRow(self._name_label, self._name_edit)
        if self._multi:
            # Hide both label and field by removing visibility
            self._name_label.setVisible(False)
            self._name_edit.setVisible(False)

        self._descr_edit = QPlainTextEdit()
        self._descr_edit.setFixedHeight(72)
        form.addRow("Description:", self._descr_edit)

        self._password_edit = QLineEdit()
        form.addRow("Password:", self._password_edit)

        self._price_spin = QDoubleSpinBox()
        self._price_spin.setDecimals(2)
        self._price_spin.setRange(0.00, 99.99)
        self._price_spin.setSingleStep(0.50)
        self._price_spin.setSuffix(" USD")
        form.addRow("Price:", self._price_spin)

        self._public_check = QCheckBox("Publicly listed")
        self._premium_check = QCheckBox("Premium members only")
        if self._multi:
            self._public_check.setTristate(True)
            self._premium_check.setTristate(True)
            self._public_check.setCheckState(Qt.CheckState.PartiallyChecked)
            self._premium_check.setCheckState(Qt.CheckState.PartiallyChecked)
        form.addRow("Flags:", self._public_check)
        form.addRow("", self._premium_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_from_initial(self):
        self._name_edit.setText(self._initial.get("file_name", ""))
        self._descr_edit.setPlainText(self._initial.get("file_descr", ""))
        self._password_edit.setText(self._initial.get("file_password", ""))
        try:
            price = float(self._initial.get("file_price", "0") or "0")
        except ValueError:
            price = 0.0
        self._price_spin.setValue(max(0.0, min(99.99, price)))
        self._public_check.setChecked(self._initial.get("file_public") == "1")
        self._premium_check.setChecked(
            self._initial.get("file_premium_only") == "1"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_changed_fields(self) -> Dict[str, str]:
        """Return a dict of only the fields the user actually modified."""
        if self._multi:
            return self._diff_multi()
        return self._diff_single()

    def _diff_single(self) -> Dict[str, str]:
        diff: Dict[str, str] = {}

        name = self._name_edit.text()
        if name != self._initial.get("file_name", ""):
            diff["file_name"] = name

        descr = self._descr_edit.toPlainText()
        if descr != self._initial.get("file_descr", ""):
            diff["file_descr"] = descr

        password = self._password_edit.text()
        if password != self._initial.get("file_password", ""):
            diff["file_password"] = password

        price_str = f"{self._price_spin.value():.2f}"
        if price_str != self._initial.get("file_price", "0.00"):
            diff["file_price"] = price_str

        pub = "1" if self._public_check.isChecked() else "0"
        if pub != self._initial.get("file_public", "0"):
            diff["file_public"] = pub

        prem = "1" if self._premium_check.isChecked() else "0"
        if prem != self._initial.get("file_premium_only", "0"):
            diff["file_premium_only"] = prem

        return diff

    def _diff_multi(self) -> Dict[str, str]:
        diff: Dict[str, str] = {}

        # file_name is intentionally excluded in multi mode — the
        # controller will drop it even if the widget was somehow shown.

        descr = self._descr_edit.toPlainText()
        if descr:
            diff["file_descr"] = descr

        password = self._password_edit.text()
        if password:
            diff["file_password"] = password

        if self._price_spin.value() > 0:
            diff["file_price"] = f"{self._price_spin.value():.2f}"

        pub_state = self._public_check.checkState()
        if pub_state == Qt.CheckState.Checked:
            diff["file_public"] = "1"
        elif pub_state == Qt.CheckState.Unchecked:
            diff["file_public"] = "0"

        prem_state = self._premium_check.checkState()
        if prem_state == Qt.CheckState.Checked:
            diff["file_premium_only"] = "1"
        elif prem_state == Qt.CheckState.Unchecked:
            diff["file_premium_only"] = "0"

        return diff
