"""Filespace folder row regex extracts file_count into FileInfo.metadata."""
from pathlib import Path
from unittest.mock import MagicMock

from src.network.file_manager.filespace_client import FilespaceFileManagerClient


def test_folder_row_carries_file_count():
    html = Path("logs/filespace.htm").read_text()
    fhc = MagicMock()
    fhc.config.requires_auth = True
    fm = FilespaceFileManagerClient(file_host_client=fhc)
    fm._web_get = lambda url: html

    folders, _files = fm._scrape_page("0", page=1)
    assert any(f.id == "33018" for f in folders), "expected fixture folder"
    sub = next(f for f in folders if f.id == "33018")
    assert sub.metadata.get("file_count") == 0


def test_folder_count_with_nonzero_value():
    html = """
    <TR>
        <TD style="text-align:center;"><img src="/images/folder.gif" alt="Folder"></TD>
        <TD style="width:95%;"><a href="?op=my_files&amp;fld_id=42"><b>archive</b></a></TD>
        <TD style="white-space:nowrap;text-align:right;">17 files</TD>
    </TR>
    """
    fhc = MagicMock()
    fhc.config.requires_auth = True
    fm = FilespaceFileManagerClient(file_host_client=fhc)
    fm._web_get = lambda url: html

    folders, _files = fm._scrape_page("0", page=1)
    match = [f for f in folders if f.id == "42"]
    assert match and match[0].metadata["file_count"] == 17
