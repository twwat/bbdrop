"""
Comprehensive test suite for src/processing/archive_coordinator.py
Tests archive processing workflow with extraction, folder selection, and cleanup.
"""

from pathlib import Path
from unittest.mock import Mock, patch

from src.processing.archive_coordinator import ArchiveCoordinator


class TestArchiveCoordinatorInit:
    """Test ArchiveCoordinator initialization"""

    def test_init_with_parent_widget(self):
        """Test initialization with parent widget"""
        mock_service = Mock()
        mock_parent = Mock()

        coordinator = ArchiveCoordinator(mock_service, mock_parent)

        assert coordinator.service is mock_service
        assert coordinator.parent is mock_parent

    def test_init_without_parent_widget(self):
        """Test initialization without parent widget"""
        mock_service = Mock()

        coordinator = ArchiveCoordinator(mock_service)

        assert coordinator.service is mock_service
        assert coordinator.parent is None

    def test_init_with_none_parent(self):
        """Test initialization with explicit None parent"""
        mock_service = Mock()

        coordinator = ArchiveCoordinator(mock_service, None)

        assert coordinator.service is mock_service
        assert coordinator.parent is None


class TestArchiveCoordinatorProcessArchiveBasic:
    """Test basic process_archive functionality"""

    def test_process_archive_with_string_path(self):
        """Test process_archive converts string path to Path"""
        mock_service = Mock()
        mock_service.extract_archive.return_value = Path("/tmp/extract_test")
        mock_service.get_folders.return_value = [Path("/tmp/extract_test/folder1")]
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            result = coordinator.process_archive("/path/to/archive.zip")

        assert result == [Path("/tmp/extract_test/folder1")]
        assert isinstance(result[0], Path)

    def test_process_archive_with_path_object(self):
        """Test process_archive accepts Path objects"""
        mock_service = Mock()
        archive_path = Path("/path/to/archive.zip")
        mock_service.extract_archive.return_value = Path("/tmp/extract_test")
        mock_service.get_folders.return_value = [Path("/tmp/extract_test/folder1")]
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            result = coordinator.process_archive(archive_path)

        assert result == [Path("/tmp/extract_test/folder1")]
        mock_service.extract_archive.assert_called_once_with(archive_path)


class TestArchiveCoordinatorExtraction:
    """Test archive extraction phase"""

    def test_extract_archive_success(self):
        """Test successful archive extraction"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = [Path("/tmp/extract_test/folder1")]
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            result = coordinator.process_archive(Path("/archive.zip"))

        mock_service.extract_archive.assert_called_once()
        assert result is not None

    def test_extract_archive_failure_returns_none(self):
        """Test extraction failure returns None"""
        mock_service = Mock()
        mock_service.extract_archive.return_value = None

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            result = coordinator.process_archive(Path("/archive.zip"))

        assert result is None
        mock_service.cleanup_temp_dir.assert_not_called()

    def test_extract_archive_calls_service(self):
        """Test that extract_archive is called with archive path"""
        mock_service = Mock()
        archive_path = Path("/path/to/archive.zip")
        mock_service.extract_archive.return_value = None

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            coordinator.process_archive(archive_path)

        mock_service.extract_archive.assert_called_once_with(archive_path)


class TestArchiveCoordinatorFolderRetrieval:
    """Test folder retrieval phase"""

    def test_get_folders_called_after_extraction(self):
        """Test get_folders is called with extracted temp_dir"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = [Path("/tmp/extract_test/folder1")]
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            coordinator.process_archive(Path("/archive.zip"))

        mock_service.get_folders.assert_called_once_with(temp_dir)

    def test_no_folders_found_cleanup_and_return_none(self):
        """Test returns None and cleans up when no folders found"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = []
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            result = coordinator.process_archive(Path("/archive.zip"))

        assert result is None
        mock_service.cleanup_temp_dir.assert_called_once_with(temp_dir)


class TestArchiveCoordinatorSingleFolder:
    """Test handling of single folder case"""

    def test_single_folder_returns_directly_without_dialog(self):
        """Test single folder is returned without showing dialog"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folder = Path("/tmp/extract_test/folder1")
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = [folder]
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            result = coordinator.process_archive(Path("/archive.zip"))

            assert result == [folder]
            mock_dialog_class.assert_not_called()

    def test_single_folder_no_cleanup_needed(self):
        """Test single folder doesn't trigger cleanup"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folder = Path("/tmp/extract_test/folder1")
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = [folder]

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            coordinator.process_archive(Path("/archive.zip"))

        mock_service.cleanup_temp_dir.assert_not_called()


class TestArchiveCoordinatorMultipleFolders:
    """Test handling of multiple folders case"""

    def test_multiple_folders_shows_dialog(self):
        """Test multiple folders triggers folder selector dialog"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test_archive'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = [folders[0]]
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

            assert result == [folders[0]]
            mock_dialog_class.assert_called_once_with('test_archive', folders, None)
            mock_dialog.exec.assert_called_once()

    def test_multiple_folders_with_parent_widget(self):
        """Test dialog receives parent widget"""
        mock_service = Mock()
        mock_parent = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service, mock_parent)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = [folders[0]]
            mock_dialog_class.return_value = mock_dialog

            coordinator.process_archive(Path("/archive.zip"))

            mock_dialog_class.assert_called_once_with('test', folders, mock_parent)

    def test_dialog_with_three_folders(self):
        """Test dialog with exactly three folders"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2"),
            Path("/tmp/extract_test/folder3")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = [folders[0], folders[2]]
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

            assert result == [folders[0], folders[2]]


class TestArchiveCoordinatorDialogCancellation:
    """Test dialog cancellation handling"""

    def test_dialog_cancelled_returns_none(self):
        """Test cancellation returns None"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = False
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

            assert result is None

    def test_dialog_cancelled_triggers_cleanup(self):
        """Test cancellation triggers temp directory cleanup"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = False
            mock_dialog_class.return_value = mock_dialog

            coordinator.process_archive(Path("/archive.zip"))

            mock_service.cleanup_temp_dir.assert_called_once_with(temp_dir)

    def test_dialog_accepted_but_no_selection_returns_none(self):
        """Test dialog accepted but no folders selected returns None"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = []
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

            assert result is None

    def test_dialog_accepted_no_selection_triggers_cleanup(self):
        """Test dialog accepted with no selection triggers cleanup"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = []
            mock_dialog_class.return_value = mock_dialog

            coordinator.process_archive(Path("/archive.zip"))

            mock_service.cleanup_temp_dir.assert_called_once_with(temp_dir)


class TestArchiveCoordinatorDialogSelection:
    """Test dialog selection handling"""

    def test_dialog_returns_selected_folders(self):
        """Test dialog selection returns chosen folders"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2"),
            Path("/tmp/extract_test/folder3")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            selected = [folders[0], folders[2]]
            mock_dialog.get_selected_folders.return_value = selected
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

            assert result == selected

    def test_dialog_selection_no_cleanup(self):
        """Test successful selection doesn't trigger cleanup"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = [folders[0]]
            mock_dialog_class.return_value = mock_dialog

            coordinator.process_archive(Path("/archive.zip"))

            mock_service.cleanup_temp_dir.assert_not_called()


class TestArchiveCoordinatorArchiveNameHandling:
    """Test archive name handling in dialog"""

    def test_archive_name_extracted_from_path(self):
        """Test archive name is extracted and passed to dialog"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [
            Path("/tmp/extract_test/folder1"),
            Path("/tmp/extract_test/folder2")
        ]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='my_archive_name') as mock_get_name, \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = [folders[0]]
            mock_dialog_class.return_value = mock_dialog

            archive_path = Path("/path/to/my_archive.zip")
            coordinator.process_archive(archive_path)

            mock_get_name.assert_called_once_with(archive_path)
            mock_dialog_class.assert_called_once()
            call_args = mock_dialog_class.call_args
            assert call_args[0][0] == 'my_archive_name'

    def test_archive_name_with_windows_path(self):
        """Test archive name handling with Windows-style paths"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [Path("/tmp/extract_test/folder1")]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='archive') as mock_get_name, \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = [folders[0]]
            mock_dialog_class.return_value = mock_dialog

            coordinator.process_archive(Path("C:\\Users\\test\\archive.zip"))

            mock_get_name.assert_called_once()


class TestArchiveCoordinatorEdgeCases:
    """Test edge cases and error conditions"""

    def test_process_archive_empty_string_path(self):
        """Test process_archive with empty string path"""
        mock_service = Mock()
        mock_service.extract_archive.return_value = None

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value=''):
            result = coordinator.process_archive("")

        assert result is None

    def test_process_archive_path_with_spaces(self):
        """Test process_archive with path containing spaces"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract test")
        folders = [Path("/tmp/extract test/folder1")]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='my archive'):
            result = coordinator.process_archive(Path("/path/my archive.zip"))

        assert result == folders

    def test_process_archive_many_folders(self):
        """Test process_archive with many folders"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_test")
        folders = [Path(f"/tmp/extract_test/folder{i}") for i in range(10)]
        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = folders[::2]
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

            assert len(result) == 5


class TestArchiveCoordinatorIntegration:
    """Integration-level tests"""

    def test_full_workflow_single_folder(self):
        """Test complete workflow with single folder"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_archive")
        folder = Path("/tmp/extract_archive/images")

        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = [folder]

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='archive'):
            result = coordinator.process_archive(Path("/path/archive.zip"))

        assert result == [folder]
        mock_service.extract_archive.assert_called_once()
        mock_service.get_folders.assert_called_once()
        mock_service.cleanup_temp_dir.assert_not_called()

    def test_full_workflow_multiple_folders_user_selects(self):
        """Test complete workflow with multiple folders and user selection"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_archive")
        folders = [
            Path("/tmp/extract_archive/folder1"),
            Path("/tmp/extract_archive/folder2"),
            Path("/tmp/extract_archive/folder3")
        ]

        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = True
            mock_dialog.get_selected_folders.return_value = [folders[0], folders[2]]
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

        assert result == [folders[0], folders[2]]
        mock_service.extract_archive.assert_called_once()
        mock_service.get_folders.assert_called_once()
        mock_service.cleanup_temp_dir.assert_not_called()

    def test_full_workflow_extraction_fails(self):
        """Test complete workflow when extraction fails"""
        mock_service = Mock()
        mock_service.extract_archive.return_value = None

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'):
            result = coordinator.process_archive(Path("/archive.zip"))

        assert result is None
        mock_service.extract_archive.assert_called_once()
        mock_service.get_folders.assert_not_called()
        mock_service.cleanup_temp_dir.assert_not_called()

    def test_full_workflow_user_cancels(self):
        """Test complete workflow when user cancels dialog"""
        mock_service = Mock()
        temp_dir = Path("/tmp/extract_archive")
        folders = [
            Path("/tmp/extract_archive/folder1"),
            Path("/tmp/extract_archive/folder2")
        ]

        mock_service.extract_archive.return_value = temp_dir
        mock_service.get_folders.return_value = folders
        mock_service.cleanup_temp_dir.return_value = True

        coordinator = ArchiveCoordinator(mock_service)

        with patch('src.processing.archive_coordinator.get_archive_name', return_value='test'), \
             patch('src.processing.archive_coordinator.ArchiveFolderSelector') as mock_dialog_class:

            mock_dialog = Mock()
            mock_dialog.exec.return_value = False
            mock_dialog_class.return_value = mock_dialog

            result = coordinator.process_archive(Path("/archive.zip"))

        assert result is None
        mock_service.cleanup_temp_dir.assert_called_once_with(temp_dir)
