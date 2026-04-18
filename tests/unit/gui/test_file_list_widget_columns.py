"""Tests for the new Gallery / Downloads / Last DL columns on FileListWidget."""
from src.network.file_manager.client import FileInfo, FileListResult


def test_columns_include_gallery_downloads_last_dl(qtbot):
    from src.gui.widgets.file_list_widget import FileListWidget
    w = FileListWidget()
    qtbot.addWidget(w)

    headers = [
        w._table.horizontalHeaderItem(i).text()
        for i in range(w._table.columnCount())
    ]
    assert "Gallery" in headers
    assert "Downloads" in headers
    assert "Last DL" in headers


def test_set_files_populates_downloads_from_metadata(qtbot):
    from src.gui.widgets.file_list_widget import (
        FileListWidget, COL_DOWNLOADS, COL_LAST_DL,
    )
    w = FileListWidget()
    qtbot.addWidget(w)

    fi = FileInfo(
        id="abc",
        name="x.zip",
        is_folder=False,
        size=100,
        metadata={"nb_downloads": 42},
    )
    result = FileListResult(files=[fi], total=1, page=1, per_page=100)
    w.set_files(result)

    assert w._table.item(0, COL_DOWNLOADS).text() == "42"


def test_set_files_populates_last_dl_from_metadata(qtbot):
    from src.gui.widgets.file_list_widget import FileListWidget, COL_LAST_DL
    w = FileListWidget()
    qtbot.addWidget(w)

    # K2S format: nested extended_info with date_download_last.
    fi = FileInfo(
        id="abc",
        name="x.zip",
        is_folder=False,
        metadata={"extended_info": {"date_download_last": "2025-06-01 12:00:00"}},
    )
    result = FileListResult(files=[fi], total=1, page=1, per_page=100)
    w.set_files(result)

    cell = w._table.item(0, COL_LAST_DL).text()
    assert cell.startswith("2025-06-01")


def test_blank_cells_for_hosts_without_data(qtbot):
    from src.gui.widgets.file_list_widget import (
        FileListWidget, COL_DOWNLOADS, COL_LAST_DL, COL_GALLERY,
    )
    w = FileListWidget()
    qtbot.addWidget(w)

    fi = FileInfo(id="abc", name="x.zip", is_folder=False)  # empty metadata
    result = FileListResult(files=[fi], total=1, page=1, per_page=100)
    w.set_files(result)

    assert w._table.item(0, COL_DOWNLOADS).text() == ""
    assert w._table.item(0, COL_LAST_DL).text() == ""
    assert w._table.item(0, COL_GALLERY).text() == ""


def test_gallery_column_populated_when_gallery_map_set(qtbot):
    from src.gui.widgets.file_list_widget import FileListWidget, COL_GALLERY
    w = FileListWidget()
    qtbot.addWidget(w)

    fi = FileInfo(id="abc123", name="x.zip", is_folder=False)
    result = FileListResult(files=[fi], total=1, page=1, per_page=100)

    w.set_gallery_map({"abc123": "My Gallery"})
    w.set_files(result)

    assert w._table.item(0, COL_GALLERY).text() == "My Gallery"


def test_folder_row_shows_folder_metadata_in_size_column(qtbot):
    from src.gui.widgets.file_list_widget import FileListWidget, COL_SIZE
    w = FileListWidget()
    qtbot.addWidget(w)

    fi = FileInfo(
        id="fld1",
        name="pics",
        is_folder=True,
        metadata={"nb_files": 10, "nb_folders": 2, "size_files": 1024},
    )
    result = FileListResult(files=[fi], total=1, page=1, per_page=100)
    w.set_files(result)

    cell = w._table.item(0, COL_SIZE).text()
    # Some shape like "10 files · 2 folders · 1.0 KiB" is acceptable;
    # just check the key numbers are present.
    assert "10" in cell and "2" in cell
