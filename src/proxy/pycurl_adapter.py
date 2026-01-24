"""pycurl proxy configuration adapter."""

from typing import Optional, Union
import pycurl

from src.proxy.models import ProxyProfile, ProxyEntry, ProxyType
from src.proxy.credentials import get_proxy_password
from src.utils.logger import log


# Map ProxyType to pycurl constants
PROXY_TYPE_MAP = {
    ProxyType.HTTP: pycurl.PROXYTYPE_HTTP,
    ProxyType.HTTPS: pycurl.PROXYTYPE_HTTP,  # HTTPS proxy uses HTTP CONNECT tunnel
    ProxyType.SOCKS4: pycurl.PROXYTYPE_SOCKS4,
    ProxyType.SOCKS5: pycurl.PROXYTYPE_SOCKS5,
}


class PyCurlProxyAdapter:
    """Applies proxy configuration to pycurl handles."""

    @staticmethod
    def configure_proxy(curl: pycurl.Curl, proxy: Optional[Union[ProxyEntry, ProxyProfile]]) -> None:
        """
        Configure proxy options on a pycurl handle.

        Args:
            curl: pycurl.Curl instance to configure
            proxy: ProxyEntry or ProxyProfile to apply, or None for direct connection
        """
        if proxy is None:
            curl.setopt(pycurl.PROXY, "")
            return

        if not proxy.enabled:
            curl.setopt(pycurl.PROXY, "")
            return

        if not proxy.host:
            log("Proxy has no host configured", level="warning", category="proxy")
            curl.setopt(pycurl.PROXY, "")
            return

        try:
            # Build proxy URL with appropriate scheme for HTTPS proxies
            proxy_host = proxy.host
            if proxy.proxy_type == ProxyType.HTTPS and not proxy_host.startswith(('http://', 'https://')):
                proxy_host = f"https://{proxy_host}"

            # Set proxy host and port
            curl.setopt(pycurl.PROXY, proxy_host)
            curl.setopt(pycurl.PROXYPORT, proxy.port)

            # Set proxy type
            pycurl_type = PROXY_TYPE_MAP.get(proxy.proxy_type, pycurl.PROXYTYPE_HTTP)
            curl.setopt(pycurl.PROXYTYPE, pycurl_type)

            # Set authentication
            password = None
            if isinstance(proxy, ProxyEntry):
                # ProxyEntry stores password directly
                if proxy.username and proxy.password:
                    password = proxy.password
            elif isinstance(proxy, ProxyProfile):
                # ProxyProfile uses credential storage
                if proxy.auth_required and proxy.username:
                    password = get_proxy_password(proxy.id)

            if proxy.username and password:
                curl.setopt(pycurl.PROXYUSERPWD, f"{proxy.username}:{password}")
                log(f"Proxy auth configured", level="debug", category="proxy")

            log(f"Proxy configured: {proxy.proxy_type.value}://{proxy.host}:{proxy.port}",
                level="debug", category="proxy")

        except pycurl.error as e:
            log(f"Failed to configure proxy: {e}", level="error", category="proxy")
            curl.setopt(pycurl.PROXY, "")

    @staticmethod
    def get_proxy_info_string(proxy: Optional[Union[ProxyEntry, ProxyProfile]]) -> str:
        """Get a safe-to-log string describing the proxy configuration."""
        if proxy is None:
            return "Direct connection (no proxy)"

        if not proxy.enabled:
            return "Proxy disabled"

        auth_info = " (with auth)" if proxy.username else ""
        return f"{proxy.proxy_type.value}://{proxy.host}:{proxy.port}{auth_info}"
