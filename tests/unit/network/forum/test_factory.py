import pytest

from src.network.forum import factory
from src.network.forum.vbulletin_client import VBulletinClient


def test_creates_vbulletin_client():
    client = factory.create_forum_client(
        "vbulletin_4_2_0", base_url="https://vipergirls.to"
    )
    assert isinstance(client, VBulletinClient)
    assert client.base_url == "https://vipergirls.to"


def test_strips_trailing_slash_from_base_url():
    client = factory.create_forum_client(
        "vbulletin_4_2_0", base_url="https://vipergirls.to/"
    )
    assert client.base_url == "https://vipergirls.to"


def test_unknown_software_raises():
    with pytest.raises(ValueError):
        factory.create_forum_client("does_not_exist", base_url="x")


def test_lists_supported():
    assert "vbulletin_4_2_0" in factory.supported_software_ids()


def test_register_assigns_software_id():
    assert VBulletinClient.software_id == "vbulletin_4_2_0"
