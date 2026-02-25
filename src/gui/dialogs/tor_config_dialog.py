"""Tor Configuration Dialog - Status, circuit control, and connection settings."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QGroupBox, QLineEdit, QSpinBox, QDialogButtonBox,
)
from PyQt6.QtCore import pyqtSignal
import threading


class TorConfigDialog(QDialog):
    """Dialog for Tor network configuration, status, and circuit control."""

    _tor_status_ready = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tor Network Configuration")
        self.setModal(True)
        self.resize(500, 0)

        self.setup_ui()

        self._tor_status_ready.connect(self._update_status)
        self._check_status()

    def setup_ui(self):
        from src.proxy.tor import TOR_HOST, TOR_SOCKS_PORT, TOR_CONTROL_PORT
        self._defaults = (TOR_HOST, TOR_SOCKS_PORT, TOR_CONTROL_PORT)

        layout = QVBoxLayout(self)

        # ── About ─────────────────────────────────────────────────────
        about = QLabel(
            "Tor routes traffic through multiple independent relays so no "
            "single point can see both who you are and what you are "
            "connecting to. It is significantly slower than a direct "
            "connection due to multi-hop routing."
            "<br><br>"
            "Download the <b>Tor Expert Bundle</b> (standalone daemon, no "
            "browser needed) from "
            "<a href='https://www.torproject.org/download/tor/'>"
            "torproject.org/download/tor/</a>. "
            "Extract it and run the Tor executable — it listens on port "
            "9050 by default."
            "<br><br>"
            "<b>Tor Browser</b> also works: while the browser is open, the "
            "bundled daemon listens on port 9150. Close the browser and "
            "the daemon stops."
        )
        about.setWordWrap(True)
        about.setOpenExternalLinks(True)
        layout.addWidget(about)

        # ── Status (inline) ──────────────────────────────────────────
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Checking...")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        # ── Connection ────────────────────────────────────────────────
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout(conn_group)

        conn_desc = QLabel(
            f"Default: {TOR_HOST}:{TOR_SOCKS_PORT} (SOCKS), "
            f"control port {TOR_CONTROL_PORT}. "
            "Tor Browser uses SOCKS port 9150 instead."
        )
        conn_desc.setWordWrap(True)
        conn_desc.setProperty("class", "group-description")
        conn_layout.addWidget(conn_desc)

        form = QFormLayout()
        form.setHorizontalSpacing(12)

        self.host_input = QLineEdit(TOR_HOST)
        self.host_input.setToolTip("Tor SOCKS5 proxy address")
        self.host_input.textChanged.connect(self._update_reset_visibility)
        form.addRow("Host:", self.host_input)

        self.socks_port_spin = QSpinBox()
        self.socks_port_spin.setRange(1, 65535)
        self.socks_port_spin.setValue(TOR_SOCKS_PORT)
        self.socks_port_spin.setToolTip(
            "SOCKS5 port. Default 9050 for Tor daemon, 9150 for Tor Browser."
        )
        self.socks_port_spin.valueChanged.connect(self._update_reset_visibility)
        form.addRow("SOCKS port:", self.socks_port_spin)

        self.control_port_spin = QSpinBox()
        self.control_port_spin.setRange(1, 65535)
        self.control_port_spin.setValue(TOR_CONTROL_PORT)
        self.control_port_spin.setToolTip(
            "Control port for circuit renewal. Default 9051."
        )
        self.control_port_spin.valueChanged.connect(self._update_reset_visibility)
        form.addRow("Control port:", self.control_port_spin)

        self.control_password = QLineEdit()
        self.control_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.control_password.setPlaceholderText("(leave blank if no auth)")
        self.control_password.setToolTip(
            "Password for Tor's control port. Leave blank if Tor has no "
            "authentication configured. Only needed for circuit renewal."
        )
        form.addRow("Control password:", self.control_password)

        conn_layout.addLayout(form)

        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.setToolTip(
            f"Reset to {TOR_HOST}:{TOR_SOCKS_PORT} / control {TOR_CONTROL_PORT}"
        )
        self.reset_btn.clicked.connect(self._reset_defaults)
        self.reset_btn.setVisible(False)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_row.addWidget(self.reset_btn)
        conn_layout.addLayout(reset_row)

        layout.addWidget(conn_group)

        # ── Circuit Control ───────────────────────────────────────────
        circuit_group = QGroupBox("Circuit Control")
        circuit_layout = QVBoxLayout(circuit_group)

        circuit_desc = QLabel(
            "Tor rotates your exit node automatically. Force an immediate "
            "rotation by requesting a new circuit (sends a NEWNYM signal). "
            "Takes about 10 seconds to take effect."
        )
        circuit_desc.setWordWrap(True)
        circuit_layout.addWidget(circuit_desc)

        circuit_row = QHBoxLayout()
        self.newnym_btn = QPushButton("New Circuit")
        self.newnym_btn.setToolTip("Request a new Tor exit node IP")
        self.newnym_btn.setEnabled(False)
        self.newnym_btn.clicked.connect(self._on_new_circuit)
        circuit_row.addWidget(self.newnym_btn)

        self.circuit_status = QLabel("")
        circuit_row.addWidget(self.circuit_status)
        circuit_row.addStretch()
        circuit_layout.addLayout(circuit_row)

        layout.addWidget(circuit_group)

        # ── Buttons ───────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Defaults ──────────────────────────────────────────────────────

    def _update_reset_visibility(self):
        """Show Reset to Defaults button when any connection value differs."""
        default_host, default_socks, default_control = self._defaults
        changed = (
            self.host_input.text().strip() != default_host
            or self.socks_port_spin.value() != default_socks
            or self.control_port_spin.value() != default_control
        )
        self.reset_btn.setVisible(changed)

    def _reset_defaults(self):
        """Reset connection fields to default values."""
        default_host, default_socks, default_control = self._defaults
        self.host_input.setText(default_host)
        self.socks_port_spin.setValue(default_socks)
        self.control_port_spin.setValue(default_control)

    # ── Status checking ───────────────────────────────────────────────

    def _check_status(self):
        """Check Tor status in a background thread."""
        self.status_label.setText("Checking...")
        self.status_label.setStyleSheet("")

        host = self.host_input.text().strip() or "127.0.0.1"
        port = self.socks_port_spin.value()

        def _probe():
            from src.proxy.tor import is_tor_running
            running = is_tor_running(host=host, port=port, timeout=1.5)
            self._tor_status_ready.emit(running)

        threading.Thread(target=_probe, daemon=True).start()

    def _update_status(self, running: bool):
        """Update status label on the main thread."""
        host = self.host_input.text().strip() or "127.0.0.1"
        port = self.socks_port_spin.value()
        self.newnym_btn.setEnabled(running)
        if running:
            self.status_label.setText(f"Running ({host}:{port})")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText(f"Not detected ({host}:{port})")
            self.status_label.setStyleSheet("color: red;")

    # ── Circuit control ───────────────────────────────────────────────

    def _on_new_circuit(self):
        """Request a new Tor circuit."""
        from src.proxy.tor import request_new_circuit
        host = self.host_input.text().strip() or "127.0.0.1"
        port = self.control_port_spin.value()
        password = self.control_password.text()
        success, message = request_new_circuit(
            host=host, port=port, password=password
        )
        if success:
            self.circuit_status.setText("New circuit requested")
            self.circuit_status.setStyleSheet("color: green;")
        else:
            self.circuit_status.setText(message)
            self.circuit_status.setStyleSheet("color: red;")
