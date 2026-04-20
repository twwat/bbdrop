"""Modal credential test dialog with live diagnostic log.

Runs network diagnostics (DNS, TCP, TLS) and a credential check in a
background thread, streaming log output live as each step completes.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QPlainTextEdit,
)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont


class _CredentialTestWorker(QThread):
    log_line = pyqtSignal(str)
    finished = pyqtSignal(dict)  # credentials_valid, user_info_valid, error_message

    def __init__(self, host_config, host_id: str, credentials: str):
        super().__init__()
        self._host_config = host_config
        self._host_id = host_id
        self._credentials = credentials

    def run(self):
        import socket
        import ssl
        import time as _time
        from urllib.parse import urlparse

        emit = self.log_line.emit
        results = {
            'credentials_valid': False,
            'user_info_valid': False,
            'error_message': '',
        }

        url = (
            getattr(self._host_config, 'user_info_url', None)
            or getattr(self._host_config, 'login_url', None)
            or getattr(self._host_config, 'upload_endpoint', None)
            or ""
        )

        if url:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            use_tls = parsed.scheme == 'https'

            # DNS
            emit(f"→ Resolving {hostname}...")
            t0 = _time.monotonic()
            try:
                ip = socket.gethostbyname(hostname)
                dns_ms = (_time.monotonic() - t0) * 1000
                emit(f"  {hostname} → {ip}  ({dns_ms:.0f} ms)")
            except socket.gaierror as e:
                emit(f"  DNS failed: {e}")
                self.finished.emit(results)
                return

            # TCP connect
            emit(f"")
            emit(f"→ TCP connect → {ip}:{port}...")
            t1 = _time.monotonic()
            sock = None
            try:
                sock = socket.create_connection((hostname, port), timeout=10)
                tcp_ms = (_time.monotonic() - t1) * 1000
                emit(f"  Connected in {tcp_ms:.0f} ms")
            except Exception as e:
                emit(f"  Connection failed: {e}")

            # TLS handshake
            if sock and use_tls:
                emit(f"")
                emit(f"→ TLS handshake...")
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
            emit("  (No URL available for network diagnostics)")

        # Credential test
        emit("")
        emit("→ Testing credentials...")
        try:
            from src.network.file_host_client import FileHostClient
            import time as _t

            t_start = _t.monotonic()
            client = FileHostClient(
                host_config=self._host_config,
                bandwidth_counter=None,
                credentials=self._credentials,
                host_id=self._host_id,
                log_callback=lambda msg, level="info": emit(f"  {msg}"),
            )
            cred_result = client.test_credentials()
            elapsed = (_t.monotonic() - t_start) * 1000

            if cred_result.get('success'):
                results['credentials_valid'] = True
                results['user_info_valid'] = bool(cred_result.get('user_info'))
                emit(f"  ✓ Credentials valid  ({elapsed:.0f} ms)")
                if cred_result.get('user_info'):
                    emit("  ✓ User info retrieved")
                else:
                    emit("  ○ User info: not available")
            else:
                msg = cred_result.get('message', 'Credential test failed')
                results['error_message'] = msg
                emit(f"  ✗ {msg}")

        except Exception as e:
            results['error_message'] = str(e)
            emit(f"  ✗ Error: {e}")

        self.finished.emit(results)


class CredentialTestDialog(QDialog):
    """Modal dialog that runs a credential diagnostic and streams live output.

    Starts the test immediately on open. Close button is disabled until
    the test completes.
    """

    def __init__(self, host_config, host_id: str, credentials: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Credential Test — {host_config.name}")
        self.setMinimumWidth(540)
        self.setModal(True)
        self._worker = _CredentialTestWorker(host_config, host_id, credentials)
        self._setup_ui()
        self._worker.log_line.connect(self._log.appendPlainText)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Live log
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._log.setMinimumHeight(220)
        self._log.setProperty("class", "console")
        layout.addWidget(self._log)

        # Results summary
        self._creds_label = QLabel("○ Waiting...")
        self._userinfo_label = QLabel("○ Waiting...")
        results_form = QFormLayout()
        results_form.addRow("Credentials:", self._creds_label)
        results_form.addRow("User info:", self._userinfo_label)
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
        if results.get('credentials_valid'):
            self._creds_label.setText("✓ Valid")
            self._creds_label.setProperty("class", "status-ok")
        else:
            self._creds_label.setText("✗ Failed")
            self._creds_label.setProperty("class", "status-error")
        self._creds_label.style().unpolish(self._creds_label)
        self._creds_label.style().polish(self._creds_label)

        if results.get('user_info_valid'):
            self._userinfo_label.setText("✓ Retrieved")
            self._userinfo_label.setProperty("class", "status-ok")
        else:
            self._userinfo_label.setText("○ Not available")
            self._userinfo_label.setProperty("class", "status-warning-light")
        self._userinfo_label.style().unpolish(self._userinfo_label)
        self._userinfo_label.style().polish(self._userinfo_label)

        if results.get('error_message'):
            self._error_label.setText(results['error_message'])

        self._close_btn.setEnabled(True)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        super().closeEvent(event)
