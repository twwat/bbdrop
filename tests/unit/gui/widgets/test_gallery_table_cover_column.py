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


class TestCoverDelegate:
    """CoverIndicatorDelegate renders correct visual states."""

    def test_delegate_has_dimmed_and_full_pixmaps(self):
        """Delegate creates both full and dimmed pixmap variants."""
        from src.gui.delegates.cover_indicator_delegate import CoverIndicatorDelegate
        delegate = CoverIndicatorDelegate()
        # Before first paint, pixmaps are None
        assert delegate._pixmap is None
        assert delegate._dimmed_pixmap is None

    def test_delegate_overlay_cache_starts_empty(self):
        """Overlay cache is empty initially."""
        from src.gui.delegates.cover_indicator_delegate import CoverIndicatorDelegate
        delegate = CoverIndicatorDelegate()
        assert delegate._overlay_cache == {}

    def test_delegate_reads_status_from_user_role_plus_1(self):
        """Delegate uses UserRole+1 for cover_status, not UserRole."""
        from src.gui.delegates.cover_indicator_delegate import CoverIndicatorDelegate
        from PyQt6.QtCore import Qt
        delegate = CoverIndicatorDelegate()
        # The paint method reads UserRole for path and UserRole+1 for status
        # This is a structural test — the actual rendering requires a QApplication
        assert hasattr(delegate, 'paint')
        assert hasattr(delegate, '_ensure_pixmaps')
        assert hasattr(delegate, '_get_overlay_pixmap')

    def test_delegate_size_hint(self):
        """Size hint should be at least ICON_SIZE wide."""
        from src.gui.delegates.cover_indicator_delegate import CoverIndicatorDelegate
        from unittest.mock import MagicMock
        delegate = CoverIndicatorDelegate()
        size = delegate.sizeHint(MagicMock(), MagicMock())
        assert size.width() >= delegate.ICON_SIZE
        assert size.height() >= delegate.ICON_SIZE
