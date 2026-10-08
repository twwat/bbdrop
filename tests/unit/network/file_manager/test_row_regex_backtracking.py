"""XFS-web row regexes must stay inside one table row.

A file-row regex whose lazy ``.*?`` segments can run past ``</tr>`` backtracks
across the rest of the page for every row that doesn't fit the pattern. When
Filedot switched its file links to ``filedot.st``, every row stopped matching
and parsing one 1.3 MB listing page held the GIL for hours, freezing the GUI
during a Link Scanner run.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from src.network.file_manager.filedot_client import FiledotFileManagerClient
from src.network.file_manager.filespace_client import FilespaceFileManagerClient


def _bare(cls):
    c = cls.__new__(cls)
    c._action_token = None
    c._file_code_to_numeric = None
    c._last_folder_id = None
    c._known_folder_ids = set()
    c._last_list_fld_id = "0"
    return c


def _filedot_row(numeric_id: int, link: str) -> str:
    # Mirrors the live markup captured 2026-10-08.
    return (
        '<tr class="filerow">\n'
        f'<td class=""><input type="checkbox" name="file_id" value="{numeric_id}"></td>\n'
        f'<td class="filename"><a href="{link}">archive{numeric_id}.zip</a> </td>\n'
        '<td class="tdinfo">1.5 MB</td>\n<td class="tdinfo">2026-10-07</td>\n'
        '<td class="tdinfo">-</td>\n<td class="tdinfo"></td>\n'
        f'<td class="icontd"><input type="checkbox" name="file_public" '
        f'onClick="setFileFlag([{numeric_id}], \'file_public\', this.checked);"></td>\n'
        f'<td class="icontd"><a href="https://filedot.to/file_edit?file_code=c{numeric_id}" '
        'name="edit"><img src="https://filedot.to/images/ico_edit.png"></a></td>\n'
        '</tr>\n'
    )


def _filespace_row(numeric_id: int, link: str) -> str:
    return (
        '<TR align=center class="hi">\n'
        f'<TD><input type="checkbox" name="file_id" value="{numeric_id}"></TD>\n'
        f'<TD align=left> <a href="{link}">archive{numeric_id}.zip</a> </TD>\n'
        '<TD align=right> 24.1 MB </TD>\n<TD> </TD>\n'
        f'<TD class=\'pub\'><input type="checkbox" name="pub" value="1" '
        f'onClick="jah(\'?op=my_files&amp;file_id={numeric_id}&amp;set_public=\'+this.checked)"></TD>\n'
        '<TD> 2026-03-18 </TD>\n'
        '</TR>\n'
    )


def _timed_scrape(client, html: str):
    with patch.object(client, "_web_get", return_value=html):
        start = time.perf_counter()
        folders, files = client._scrape_page("0", 1)
        return folders, files, time.perf_counter() - start


def test_filedot_parses_filedot_st_links():
    c = _bare(FiledotFileManagerClient)
    html = _filedot_row(1734952, "https://filedot.st/qi1ewfwr16dp")

    _folders, files, _elapsed = _timed_scrape(c, html)

    assert [f.id for f in files] == ["qi1ewfwr16dp"]
    assert files[0].name == "archive1734952.zip"
    assert files[0].size > 0
    assert c._file_code_to_numeric == {"qi1ewfwr16dp": "1734952"}


def test_filedot_unmatched_rows_do_not_backtrack_across_page():
    c = _bare(FiledotFileManagerClient)
    # Links in a shape the regex doesn't recognise: every row fails to match.
    html = "".join(
        _filedot_row(1000 + i, f"https://cdn.example/f/c{i}") for i in range(400)
    )

    _folders, files, elapsed = _timed_scrape(c, html)

    assert files == []
    assert elapsed < 1.0, f"row regex took {elapsed:.1f}s on 400 unmatched rows"


def test_filespace_unmatched_rows_do_not_backtrack_across_page():
    c = _bare(FilespaceFileManagerClient)
    html = "".join(
        _filespace_row(7000 + i, f"https://cdn.example/f/c{i}") for i in range(400)
    )

    _folders, files, elapsed = _timed_scrape(c, html)

    assert files == []
    assert elapsed < 1.0, f"row regex took {elapsed:.1f}s on 400 unmatched rows"


def test_filedot_logs_unreadable_rows_with_their_domain():
    c = _bare(FiledotFileManagerClient)
    html = _filedot_row(1, "https://filedot.to/goodcode1") + "".join(
        _filedot_row(10 + i, f"https://fdot.cc/newcode{i}") for i in range(3)
    )

    with patch("src.network.file_manager.xfs_web_client.log") as mock_log:
        _folders, files, _elapsed = _timed_scrape(c, html)

    assert [f.id for f in files] == ["goodcode1"]
    warnings = [call for call in mock_log.call_args_list
                if call.kwargs.get("level") == "warning"]
    assert len(warnings) == 1
    message = warnings[0].args[0]
    assert "Filedot" in message
    assert "3 of 4" in message
    assert "fdot.cc" in message


def test_unreadable_row_warning_is_logged_once_per_client():
    c = _bare(FiledotFileManagerClient)
    html = _filedot_row(10, "https://fdot.cc/newcode")

    with patch("src.network.file_manager.xfs_web_client.log") as mock_log:
        _timed_scrape(c, html)
        _timed_scrape(c, html)

    warnings = [call for call in mock_log.call_args_list
                if call.kwargs.get("level") == "warning"]
    assert len(warnings) == 1


def test_fully_readable_page_logs_no_warning():
    c = _bare(FilespaceFileManagerClient)
    html = _filespace_row(7000, "https://filespace.com/abc123")

    with patch("src.network.file_manager.xfs_web_client.log") as mock_log:
        _folders, files, _elapsed = _timed_scrape(c, html)

    assert [f.id for f in files] == ["abc123"]
    assert not [call for call in mock_log.call_args_list
                if call.kwargs.get("level") == "warning"]
