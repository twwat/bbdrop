"""Tests for ForumController multi-destination dispatch (v2)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_handle_gallery_uploaded_dispatches_per_destination():
    from src.gui.forum_controller import ForumController

    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True

    dests = [
        {"forum_fk": 1, "target_id": "10", "kind": "reply",
         "body_template_name": "t.txt", "forum_name": "F1"},
        {"forum_fk": 2, "target_id": "20", "kind": "new_thread",
         "body_template_name": "t.txt", "forum_name": "F2"},
    ]
    settings = {"trigger_mode": "auto_on_upload", "enabled": 1}

    with patch("src.gui.forum_controller.fp") as mock_fp:
        mock_fp.get_tab_posting_settings_for_gallery.return_value = settings
        mock_fp.get_effective_destinations.return_value = dests
        mock_fp.insert_forum_post.side_effect = [101, 102]
        mock_fp.list_forum_posts_for_gallery.return_value = []

        ctrl = ForumController(worker=mock_worker)
        ctrl._conn = MagicMock()
        ctrl._template_renderer = lambda gid, body_tpl, title_tpl: ("Body", "Title")

        result = ctrl.handle_gallery_uploaded(gallery_id=5)

    assert isinstance(result, list)
    assert len(result) == 2
    assert 101 in result
    assert 102 in result


@pytest.mark.unit
def test_handle_gallery_uploaded_skips_when_trigger_not_auto():
    from src.gui.forum_controller import ForumController

    mock_worker = MagicMock()
    settings = {"trigger_mode": "manual", "enabled": 1}

    with patch("src.gui.forum_controller.fp") as mock_fp:
        mock_fp.get_tab_posting_settings_for_gallery.return_value = settings

        ctrl = ForumController(worker=mock_worker)
        ctrl._conn = MagicMock()

        result = ctrl.handle_gallery_uploaded(gallery_id=5)

    assert result == []


@pytest.mark.unit
def test_handle_gallery_uploaded_skips_when_no_settings():
    from src.gui.forum_controller import ForumController

    mock_worker = MagicMock()

    with patch("src.gui.forum_controller.fp") as mock_fp:
        mock_fp.get_tab_posting_settings_for_gallery.return_value = None

        ctrl = ForumController(worker=mock_worker)
        ctrl._conn = MagicMock()

        result = ctrl.handle_gallery_uploaded(gallery_id=5)

    assert result == []


@pytest.mark.unit
def test_quick_post_dispatches_all_destinations():
    from src.gui.forum_controller import ForumController

    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True

    dests = [
        {"forum_fk": 1, "target_id": "10", "kind": "reply",
         "body_template_name": "t.txt", "forum_name": "F1"},
    ]

    with patch("src.gui.forum_controller.fp") as mock_fp:
        mock_fp.get_effective_destinations.return_value = dests
        mock_fp.insert_forum_post.return_value = 201

        ctrl = ForumController(worker=mock_worker)
        ctrl._conn = MagicMock()
        ctrl._template_renderer = lambda gid, body_tpl, title_tpl: ("Body", "Title")

        result = ctrl.quick_post(gallery_ids=[7])

    assert isinstance(result, dict)
    assert 7 in result
    assert result[7] == [201]


@pytest.mark.unit
def test_post_now_dispatches_given_destinations():
    from src.gui.forum_controller import ForumController

    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True

    dests = [
        {"forum_fk": 1, "target_id": "10", "kind": "reply",
         "body_template_name": "t.txt", "forum_name": "F1"},
        {"forum_fk": 1, "target_id": "20", "kind": "new_thread",
         "body_template_name": "t.txt", "forum_name": "F1"},
    ]

    with patch("src.gui.forum_controller.fp") as mock_fp:
        mock_fp.insert_forum_post.side_effect = [301, 302]

        ctrl = ForumController(worker=mock_worker)
        ctrl._conn = MagicMock()
        ctrl._template_renderer = lambda gid, body_tpl, title_tpl: ("Body", "Title")

        result = ctrl.post_now(gallery_id=9, destinations=dests)

    assert isinstance(result, list)
    assert result == [301, 302]
