"""Tests for cover indicator column in gallery queue table."""


class TestCoverColumn:
    """Gallery table has a cover indicator column."""

    def test_cover_column_exists(self):
        from src.gui.widgets.gallery_table import GalleryTableWidget
        column_names = [col[1] for col in GalleryTableWidget.COLUMNS]
        assert 'COVER' in column_names

    def test_cover_column_is_narrow(self):
        from src.gui.widgets.gallery_table import GalleryTableWidget
        for col in GalleryTableWidget.COLUMNS:
            if col[1] == 'COVER':
                width = col[3]
                assert 24 <= width <= 34
                break

    def test_cover_column_has_attribute(self):
        from src.gui.widgets.gallery_table import GalleryTableWidget
        assert hasattr(GalleryTableWidget, 'COL_COVER')

    def test_cover_column_after_status(self):
        from src.gui.widgets.gallery_table import GalleryTableWidget
        assert GalleryTableWidget.COL_COVER == GalleryTableWidget.COL_STATUS + 1

    def test_col_indices_consistent(self):
        """All COL_ attributes match their COLUMNS tuple index."""
        from src.gui.widgets.gallery_table import GalleryTableWidget
        for idx, name, *_ in GalleryTableWidget.COLUMNS:
            attr = f'COL_{name}'
            assert getattr(GalleryTableWidget, attr) == idx, f"{attr} is {getattr(GalleryTableWidget, attr)} but COLUMNS says {idx}"

    def test_table_row_manager_col_matches(self):
        """_Col in table_row_manager matches GalleryTableWidget."""
        from src.gui.widgets.gallery_table import GalleryTableWidget
        from src.gui.table_row_manager import _Col
        assert _Col.COVER == GalleryTableWidget.COL_COVER
        assert _Col.STATUS == GalleryTableWidget.COL_STATUS
        assert _Col.STATUS_TEXT == GalleryTableWidget.COL_STATUS_TEXT
        assert _Col.HOSTS_STATUS == GalleryTableWidget.COL_HOSTS_STATUS
        assert _Col.ONLINE_IMX == GalleryTableWidget.COL_ONLINE_IMX
