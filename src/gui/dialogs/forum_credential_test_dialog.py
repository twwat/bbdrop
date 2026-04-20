"""Modal forum login test dialog with live diagnostic log.

Mirrors src/gui/dialogs/credential_test_dialog.py: runs DNS, TCP, TLS
probes against the forum base URL, then calls ForumClient.authenticate
in a background thread, streaming log output live as each step completes.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QPlainTextEdit,
)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont


class _ForumLoginTestWorker(QThread):
    log_line = pyqtSignal(str)
    finished = pyqtSignal(dict)  # login_valid, username, error_message

    def __init__(self, software_id: str, base_url: str, username: str, password: str):
        super().__init__()
        self._software_id = software_id
        self._base_url = base_url
        self._username = username
        self._password = password

    def run(self):
        import socket
        import ssl
        import time as _time
        from urllib.parse import urlparse

        emit = self.log_line.emit
        results = {
            'login_valid': False,
            'username': '',
            'error_message': '',
        }

        url = self._base_url
        if url:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            use_tls = parsed.scheme == 'https'

            emit(f"→ Resolving {hostname}...")
            t0 = _time.monotonic()
            try:
                ip = socket.gethostbyname(hostname)
                dns_ms = (_time.monotonic() - t0) * 1000
                emit(f"  {hostname} → {ip}  ({dns_ms:.0f} ms)")
            except socket.gaierror as e:
                emit(f"  DNS failed: {e}")
                results['error_message'] = f"DNS failed: {e}"
                self.finished.emit(results)
                return

            emit("")
            emit(f"→ TCP connect → {ip}:{port}...")
            t1 = _time.monotonic()
            sock = None
            try:
                sock = socket.create_connection((hostname, port), timeout=10)
                tcp_ms = (_time.monotonic() - t1) * 1000
                emit(f"  Connected in {tcp_ms:.0f} ms")
            except Exception as e:
                emit(f"  Connection failed: {e}")

            if sock and use_tls:
                emit("")
                emit("→ TLS handshake...")
                t2 = _time.monotonic()
                try:
                    ctx = ssl.create_default_context()
                    ssock = ctx.wrap_socket(sock, server_hostname=hostname)
                    tls_ms = (_time.monotonic() - t2) * 1000
                    cipher_info = ssock.cipher()
                    tls_ver = ssock.version() or "unknown"
                    cipher_name = cipher_info[0] if cipher_info else "unknown"
                    emit(f"  {tls_ver}  ·  {cipher_name}  ({tls_ms:.0f} ms)")
                    ssock.close()
                    sock = None
                except ssl.SSLError as e:
                    emit(f"  TLS failed: {e}")
                    if sock:
                        sock.close()
                    sock = None
            elif sock:
                sock.close()
        else:
            emit("  (No Base URL — skipping network diagnostics)")

        emit("")
        emit("→ Testing login...")
        try:
            from src.network.forum.factory import create_forum_client
            from src.network.forum.session_store import SessionStore
            import time as _t

            t_start = _t.monotonic()
            client = create_forum_client(
                self._software_id,
                base_url=self._base_url,
                session_store=SessionStore(),
            )
            auth = client.authenticate(self._username, self._password)
            elapsed = (_t.monotonic() - t_start) * 1000

            if auth.success:
                results['login_valid'] = True
                results['username'] = auth.username or self._username
                emit(f"  ✓ Login successful  ({elapsed:.0f} ms)")
                if auth.username:
                    emit(f"  ✓ Authenticated as {auth.username}")
            else:
                msg = auth.error_message or "Login failed"
                results['error_message'] = f"{auth.error_kind} — {msg}" if auth.error_kind else msg
                emit(f"  ✗ {msg}")

        except Exception as e:
            results['error_message'] = str(e)
            emit(f"  ✗ Error: {e}")

        self.finished.emit(results)


class ForumCredentialTestDialog(QDialog):
    """Modal dialog that runs a forum login diagnostic and streams live output.

    Starts the test immediately on open. Close button is disabled until
    the test completes.
    """

    def __init__(
        self, *, forum_name: str, software_id: str, base_url: str,
        username: str, password: str, parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Forum Login Test — {forum_name}")
        self.setMinimumWidth(540)
        self.setModal(True)
        self._worker = _ForumLoginTestWorker(
            software_id, base_url, username, password,
        )
        self._setup_ui()
        self._worker.log_line.connect(self._log.appendPlainText)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._log.setMinimumHeight(220)
        self._log.setProperty("class", "console")
        layout.addWidget(self._log)

        self._login_label = QLabel("○ Waiting...")
        self._user_label = QLabel("○ Waiting...")
        results_form = QFormLayout()
        results_form.addRow("Login:", self._login_label)
        results_form.addRow("User:", self._user_label)
        layout.addLayout(results_form)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setProperty("class", "status-error")
        layout.addWidget(self._error_label)

        self._close_btn = QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def _on_finished(self, results: dict):
        if results.get('login_valid'):
            self._login_label.setText("✓ Valid")
            self._login_label.setProperty("class", "status-ok")
        else:
            self._login_label.setText("✗ Failed")
            self._login_label.setProperty("class", "status-error")
        self._login_label.style().unpolish(self._login_label)
        self._login_label.style().polish(self._login_label)

        if results.get('username'):
            self._user_label.setText(f"✓ {results['username']}")
            self._user_label.setProperty("class", "status-ok")
        else:
            self._user_label.setText("○ Not available")
            self._user_label.setProperty("class", "status-warning-light")
        self._user_label.style().unpolish(self._user_label)
        self._user_label.style().polish(self._user_label)

        if results.get('error_message'):
            self._error_label.setText(results['error_message'])

        self._close_btn.setEnabled(True)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        super().closeEvent(event)
