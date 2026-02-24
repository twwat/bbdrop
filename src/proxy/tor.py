"""Tor integration for BBDrop proxy system.

Tor is a SOCKS5 proxy at 127.0.0.1:9050. This module provides:
- Daemon detection (port check on 9050)
- One-click pool creation (SOCKS5 proxy pool with 127.0.0.1:9050)
- Circuit renewal via control port 9051 (NEWNYM signal)
- Status checking

No external dependencies — uses stdlib socket only.
"""

import socket
from typing import Tuple

from src.proxy.models import (
    ProxyEntry, ProxyPool, ProxyType, RotationStrategy,
)
from src.utils.logger import log

# Default Tor ports
TOR_SOCKS_PORT = 9050
TOR_CONTROL_PORT = 9051
TOR_HOST = "127.0.0.1"

# Well-known pool name for auto-created Tor pools
TOR_POOL_NAME = "Tor"


def is_tor_running(host: str = TOR_HOST, port: int = TOR_SOCKS_PORT,
                   timeout: float = 2.0) -> bool:
    """Check if Tor daemon is listening on the SOCKS port.

    Uses a TCP connect probe. Works on Windows.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False


def is_control_port_available(host: str = TOR_HOST, port: int = TOR_CONTROL_PORT,
                              timeout: float = 2.0) -> bool:
    """Check if Tor control port is accessible."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False


def create_tor_pool() -> ProxyPool:
    """Create a proxy pool configured for Tor SOCKS5.

    Returns a ProxyPool with a single SOCKS5 entry at 127.0.0.1:9050.
    DNS resolution is routed through the proxy to prevent leaks.
    """
    entry = ProxyEntry(
        host=TOR_HOST,
        port=TOR_SOCKS_PORT,
        proxy_type=ProxyType.SOCKS5,
        resolve_dns_through_proxy=True,
    )
    return ProxyPool(
        name=TOR_POOL_NAME,
        proxies=[entry],
        proxy_type=ProxyType.SOCKS5,
        rotation_strategy=RotationStrategy.FAILOVER,
        sticky_sessions=False,
        enabled=True,
    )


def request_new_circuit(host: str = TOR_HOST, port: int = TOR_CONTROL_PORT,
                        password: str = "", timeout: float = 5.0) -> Tuple[bool, str]:
    """Send NEWNYM signal to Tor control port to get a new circuit.

    Authentication methods supported:
    - No authentication (ControlPort with no auth configured)
    - Password authentication (HashedControlPassword in torrc)

    Cookie authentication is not implemented because on Windows,
    Tor Browser Bundle uses password auth by default and cookie auth
    requires reading a file with restrictive permissions.

    Returns:
        (success, message) tuple.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))

        # Read welcome banner (if any)
        try:
            sock.settimeout(1.0)
            sock.recv(1024)
        except socket.timeout:
            pass
        sock.settimeout(timeout)

        # Authenticate
        if password:
            sock.sendall(f'AUTHENTICATE "{password}"\r\n'.encode())
        else:
            sock.sendall(b'AUTHENTICATE\r\n')

        auth_response = sock.recv(1024).decode('utf-8', errors='replace')
        if not auth_response.startswith('250'):
            sock.close()
            return False, f"Authentication failed: {auth_response.strip()}"

        # Send NEWNYM
        sock.sendall(b'SIGNAL NEWNYM\r\n')
        newnym_response = sock.recv(1024).decode('utf-8', errors='replace')
        sock.close()

        if newnym_response.startswith('250'):
            log("Tor circuit renewal requested", level="info", category="proxy")
            return True, "New Tor circuit requested successfully"
        else:
            return False, f"NEWNYM failed: {newnym_response.strip()}"

    except socket.timeout:
        return False, f"Connection to Tor control port timed out ({host}:{port})"
    except ConnectionRefusedError:
        return False, f"Tor control port not available at {host}:{port}"
    except Exception as e:
        return False, f"Error communicating with Tor: {e}"
