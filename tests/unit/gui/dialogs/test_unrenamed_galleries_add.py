"""Adding galleries BBDrop already has back onto the IMX rename list."""

from unittest.mock import Mock, call, patch

import pytest

from src.gui.dialogs.unrenamed_galleries import (
    AddGalleriesDialog, add_galleries_to_rename_list, imx_galleries_for_rename_list)

pytestmark = pytest.mark.unit


def _item(gid, name, host='imx', finished=None, added=0):
    return {'gallery_id': gid, 'name': name, 'image_host_id': host,
            'finished_time': finished, 'added_time': added}


def test_lists_imx_galleries_not_on_the_list_newest_first():
    items = [
        _item('a1', 'Alpha', finished=100),
        _item('b2', 'Beta', finished=300),
        _item('', 'No gallery id yet', finished=400),
        _item('t1', 'On Turbo', host='turbo', finished=500),
        _item('c3', 'Already queued', finished=600),
        _item('d4', '', finished=700),
        _item('e5', 'Never finished', finished=None, added=200),
    ]
    rows = imx_galleries_for_rename_list(items, {'c3': 'Already queued'})
    assert [(gid, name) for gid, name, _ in rows] == [('b2', 'Beta'), ('e5', 'Never finished'), ('a1', 'Alpha')]


def test_add_saves_each_and_queues_on_the_running_worker():
    worker = Mock()
    with patch('src.storage.gallery_management.save_unnamed_gallery') as save:
        added = add_galleries_to_rename_list([('a1', 'Alpha'), ('b2', 'Beta')], worker)
    assert added == 2
    assert save.call_args_list == [call('a1', 'Alpha'), call('b2', 'Beta')]
    assert worker.queue_rename.call_args_list == [call('a1', 'Alpha'), call('b2', 'Beta')]


def test_add_without_a_worker_only_saves():
    with patch('src.storage.gallery_management.save_unnamed_gallery') as save:
        assert add_galleries_to_rename_list([('a1', 'Alpha')], None) == 1
    save.assert_called_once_with('a1', 'Alpha')


def test_dialog_search_filters_and_only_visible_selection_is_added(qtbot):
    dlg = AddGalleriesDialog([('a1', 'Alpha Set 1', 100), ('b2', 'Beta Set 2', 200)])
    qtbot.addWidget(dlg)
    assert dlg.table.rowCount() == 2
    assert not dlg.add_btn.isEnabled()

    dlg.search_edit.setText('beta')
    visible = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    assert [dlg.table.item(r, 1).text() for r in visible] == ['b2']

    dlg.table.selectAll()
    assert dlg.add_btn.isEnabled()
    assert dlg.selected_entries() == [('b2', 'Beta Set 2')]


def test_dialog_shows_full_names_and_ids(qtbot):
    long_name = 'Nubiles 2026-09-17 Elloise (Elfiolla, Elloise Arti, Elloize Arti, Liza A) - Set 13 1in Pink (x73)'
    dlg = AddGalleriesDialog([('1nywp', long_name, 100)])
    qtbot.addWidget(dlg)
    assert dlg.table.item(0, 0).text() == long_name
    assert dlg.table.item(0, 1).text() == '1nywp'
