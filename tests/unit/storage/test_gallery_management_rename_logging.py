"""rename_all_unnamed_with_session must not duplicate RenameWorker's success line."""

from unittest.mock import Mock, patch

import pytest

from src.storage import gallery_management


@pytest.mark.unit
def test_successful_rename_is_logged_only_by_rename_worker():
    uploader = Mock()
    uploader.rename_gallery_with_session.return_value = True
    uploader._last_rename_status_code = 200
    uploader._last_rename_ddos = False

    # remove_unnamed_gallery opens a real QueueStore and, if that fails,
    # rewrites the config file — never let the test reach it.
    with patch.object(gallery_management, 'get_unnamed_galleries',
                      return_value={'1n8lx': 'Set 7'}), \
         patch.object(gallery_management, 'remove_unnamed_gallery') as mock_remove, \
         patch.object(gallery_management, 'log') as mock_log:
        count = gallery_management.rename_all_unnamed_with_session(uploader)

    assert count == 1
    mock_remove.assert_called_once_with('1n8lx')  # proves the success path ran
    assert not any('renamed gallery' in str(c.args[0]).lower()
                   for c in mock_log.call_args_list)
