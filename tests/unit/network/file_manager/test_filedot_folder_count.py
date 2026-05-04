"""Filedot folder row regex extracts file_count into FileInfo.metadata."""
from pathlib import Path
from unittest.mock import MagicMock

from src.network.file_manager.filedot_client import FiledotFileManagerClient


def test_folder_rows_carry_file_count():
    html = Path("logs/filedot.htm").read_text()
    fhc = MagicMock()
    fhc.config.requires_auth = True
    fm = FiledotFileManagerClient(file_host_client=fhc)
    fm._web_get = lambda url: html

    folders, _files = fm._scrape_page("0", page=1)
    assert folders, "expected folder rows in fixture"
    counts = {f.id: f.metadata.get("file_count") for f in folders}
    # Spot-check known folders from the fixture (first three rows on the page).
    assert counts.get("14264") == 1055        # BoppinBabes
    assert counts.get("14435") == 150         # BratSluts
    assert counts.get("5769") == 1340         # Cartoons


def test_folder_with_zero_count_is_parsed():
    html = """
    <tr class="folderrow">
        <td class="icontd"><img></td>
        <td class="filename"><a href="https://filedot.to/files?fld_id=99">Empty</a></a></td>
        <td class="howfiles" nowrap align="center"><img>0</td>
    </tr>
    """
    fhc = MagicMock()
    fhc.config.requires_auth = True
    fm = FiledotFileManagerClient(file_host_client=fhc)
    fm._web_get = lambda url: html

    folders, _files = fm._scrape_page("0", page=1)
    assert len(folders) == 1
    assert folders[0].id == "99"
    assert folders[0].metadata["file_count"] == 0
