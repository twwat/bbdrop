"""Tests for ScreenshotSheetPreviewDialog."""


class TestScreenshotSheetPreviewDialog:
    def test_dialog_class_exists(self):
        from src.gui.dialogs.screenshot_sheet_preview import ScreenshotSheetPreviewDialog
        assert ScreenshotSheetPreviewDialog is not None

    def test_pil_to_pixmap_static_method(self):
        from src.gui.dialogs.screenshot_sheet_preview import ScreenshotSheetPreviewDialog
        assert hasattr(ScreenshotSheetPreviewDialog, '_pil_to_pixmap')

    def test_format_duration_static_method(self):
        from src.gui.dialogs.screenshot_sheet_preview import ScreenshotSheetPreviewDialog
        assert ScreenshotSheetPreviewDialog._format_duration(3661) == "1:01:01"
        assert ScreenshotSheetPreviewDialog._format_duration(125) == "2:05"
        assert ScreenshotSheetPreviewDialog._format_duration(0) == "0:00"
