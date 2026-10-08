"""Shared fixtures for service-layer tests."""

import pytest


def _remove_notifications_section():
    from src.utils.paths import read_config, get_config_path

    config = read_config()
    if config.remove_section('NOTIFICATIONS'):
        with open(get_config_path(), 'w', encoding='utf-8') as f:
            config.write(f)


@pytest.fixture
def clean_notifications_ini():
    """Start and end with no [NOTIFICATIONS] section in the (isolated) INI."""
    _remove_notifications_section()
    yield
    _remove_notifications_section()
