"""Filespace 'removed' marker maps to FileInfo.is_available=False."""
from pathlib import Path
from unittest.mock import MagicMock

from src.network.file_manager.filespace_client import FilespaceFileManagerClient


def test_removed_files_marked_unavailable():
    html = Path("logs/filespace.htm").read_text()
    fhc = MagicMock()
    fhc.config.requires_auth = True
    fm = FilespaceFileManagerClient(file_host_client=fhc)
    fm._web_get = lambda url: html

    _folders, files = fm._scrape_page("0", page=1)
    # The fixture has at least these removed file_codes:
    assert any(f.id == "kijb24lavhuv" and f.is_available is False for f in files)
    assert any(f.id == "pz4fid9ehzpk" and f.is_available is False for f in files)


def test_normal_files_remain_available():
    html = """
    <TR align=center class="hi">
        <TD><input type="checkbox" name="file_id" value="111"></TD>
        <TD align=left>
            <a href="https://filespace.com/aaaaaaaaaaaa">good.zip</a>
        </TD>
        <TD align=right>1 KB</TD>
    </TR>
    <TR align=center class="hi">
        <TD><input type="checkbox" name="file_id" value="222"></TD>
        <TD align=left>
            <a class='red' href="https://filespace.com/bbbbbbbbbbbb">bad.zip</a>
            <span class='red'> removed</span>
        </TD>
        <TD align=right>2 KB</TD>
    </TR>
    """
    fhc = MagicMock()
    fhc.config.requires_auth = True
    fm = FilespaceFileManagerClient(file_host_client=fhc)
    fm._web_get = lambda url: html

    _folders, files = fm._scrape_page("0", page=1)
    available = {f.id: f.is_available for f in files}
    assert available.get("aaaaaaaaaaaa") is True
    assert available.get("bbbbbbbbbbbb") is False
