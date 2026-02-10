"""
Factory for creating image host client instances.

Provides a unified interface to instantiate the appropriate image host
client based on the host identifier. Supports:
- 'imx' -> ImxToUploader (from bbdrop.py)
- 'turbo' -> TurboImageHostClient (from turbo_image_host_client.py)
"""

from typing import TYPE_CHECKING

from src.core.image_host_config import get_image_host_config_manager
from src.network.image_host_client import ImageHostClient

if TYPE_CHECKING:
    pass


def create_image_host_client(host_id: str) -> ImageHostClient:
    """
    Create an image host client instance for the specified host.

    Args:
        host_id: The identifier for the image host.
                 Supported values: 'imx', 'turbo'

    Returns:
        ImageHostClient: An instance of the appropriate image host client.

    Raises:
        ValueError: If the host_id is not recognized or the host
                    configuration cannot be found.

    Examples:
        >>> client = create_image_host_client('imx')
        >>> client.upload_image('/path/to/image.jpg')

        >>> turbo_client = create_image_host_client('turbo')
        >>> turbo_client.upload_image('/path/to/image.png', thumbnail_size=300)
    """
    # Verify the host exists in configuration
    config_mgr = get_image_host_config_manager()
    config = config_mgr.get_host(host_id)

    if config is None:
        available_hosts = config_mgr.list_hosts()
        raise ValueError(
            f"Unknown image host: '{host_id}'. "
            f"Available hosts: {', '.join(available_hosts) if available_hosts else 'none'}"
        )

    # Create the appropriate client based on host_id
    if host_id == "imx":
        from bbdrop import ImxToUploader
        return ImxToUploader()

    elif host_id == "turbo":
        from src.network.turbo_image_host_client import TurboImageHostClient
        return TurboImageHostClient()

    else:
        # Host exists in config but no client implementation available
        raise ValueError(
            f"No client implementation available for image host: '{host_id}'. "
            f"Configuration exists but the client class is not implemented."
        )


def get_available_hosts() -> list[str]:
    """
    Get a list of all available image host identifiers.

    Returns:
        list[str]: List of host IDs that can be used with create_image_host_client().
    """
    config_mgr = get_image_host_config_manager()
    return config_mgr.list_hosts()


def is_host_supported(host_id: str) -> bool:
    """
    Check if a host_id has a client implementation available.

    Args:
        host_id: The identifier for the image host.

    Returns:
        bool: True if the host has a client implementation, False otherwise.
    """
    supported_hosts = {"imx", "turbo"}
    return host_id in supported_hosts
