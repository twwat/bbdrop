"""Unit tests for ForumPostsStatusDelegate."""
import sys
import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.mark.unit
def test_status_color_posted_is_green():
    from src.gui.delegates.forum_posts_status_delegate import _status_color
    assert _status_color("posted").lower() == "#3d874a"


@pytest.mark.unit
def test_status_color_stale_is_orange():
    from src.gui.delegates.forum_posts_status_delegate import _status_color
    assert _status_color("stale").lower() == "#e67e22"


@pytest.mark.unit
def test_status_color_failed_is_red():
    from src.gui.delegates.forum_posts_status_delegate import _status_color
    assert _status_color("failed").lower() == "#c0392b"


@pytest.mark.unit
def test_status_color_queued_is_grey():
    from src.gui.delegates.forum_posts_status_delegate import _status_color
    assert _status_color("queued").lower() == "#888888"


@pytest.mark.unit
def test_status_color_unknown_is_grey():
    from src.gui.delegates.forum_posts_status_delegate import _status_color
    assert _status_color("anything_else").lower() == "#888888"


@pytest.mark.unit
def test_delegate_instantiates():
    from src.gui.delegates.forum_posts_status_delegate import ForumPostsStatusDelegate
    delegate = ForumPostsStatusDelegate()
    assert delegate is not None


@pytest.mark.unit
def test_delegate_has_post_clicked_signal():
    from src.gui.delegates.forum_posts_status_delegate import ForumPostsStatusDelegate
    delegate = ForumPostsStatusDelegate()
    assert hasattr(delegate, "post_clicked")
