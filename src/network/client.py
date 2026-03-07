"""
Network communication for BBDrop application.
Handles single instance server for IPC.
"""

import socket

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils.logger import log
from src.core.constants import (
    COMMUNICATION_PORT
)


class SingleInstanceServer(QThread):
    """Server for single instance communication"""

    folder_received = pyqtSignal(str)

    def __init__(self, port=COMMUNICATION_PORT):
        super().__init__()
        self.port = port
        self.running = True

    def run(self):
        """Run the single instance server"""
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('localhost', self.port))
            server_socket.listen(1)
            server_socket.settimeout(1.0)  # Timeout for checking self.running

            while self.running:
                try:
                    client_socket, _ = server_socket.accept()
                    data = client_socket.recv(1024).decode('utf-8')
                    # Emit signal for both folder paths and empty messages (window focus)
                    self.folder_received.emit(data)
                    client_socket.close()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:  # Only log if we're supposed to be running
                        log(f"Server error: {e}", level="error", category="network")

            server_socket.close()
        except Exception as e:
            log(f"Failed to start server: {e}", level="error", category="network")

    def stop(self):
        """Stop the server"""
        self.running = False
        self.wait()
