"""Per-page query-string plumbing through _folder_url for XFS-web hosts."""
from unittest.mock import MagicMock

from src.network.file_manager.filedot_client import FiledotFileManagerClient
from src.network.file_manager.filespace_client import FilespaceFileManagerClient


def _make(cls):
    fhc = MagicMock()
    fhc.config.requires_auth = True
    return cls(file_host_client=fhc)


def test_filedot_folder_url_default_no_per_page():
    fm = _make(FiledotFileManagerClient)
    url = fm._folder_url("0", page=1)
    assert "per_page" not in url
    assert "perpage" not in url


def test_filedot_folder_url_with_per_page_uses_underscore():
    fm = _make(FiledotFileManagerClient)
    url = fm._folder_url("0", page=1, per_page=5000)
    assert "per_page=5000" in url


def test_filespace_folder_url_with_per_page_uses_no_underscore():
    fm = _make(FilespaceFileManagerClient)
    url = fm._folder_url("0", page=1, per_page=500)
    assert "perpage=500" in url
    assert "per_page=" not in url


def test_scrape_page_passes_per_page_to_folder_url(monkeypatch):
    fm = _make(FiledotFileManagerClient)
    captured = {}

    def fake_web_get(url):
        captured["url"] = url
        return ""

    monkeypatch.setattr(fm, "_web_get", fake_web_get)
    fm._scrape_page("0", page=1, per_page=5000)
    assert "per_page=5000" in captured["url"]
