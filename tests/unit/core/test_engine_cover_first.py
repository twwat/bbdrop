"""Engine uploads covers first through the host client at size 5, so the first cover creates the gallery."""
import os
from unittest.mock import MagicMock

import pytest

from src.core.engine import UploadEngine

pytestmark = pytest.mark.unit

JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 100
BBCODE = '[URL=https://imx.to/i/x][IMG]https://t.imx.to/t/x.jpg[/IMG][/URL]'


def _ok(gallery_id='gal1', gallery_name=None, bbcode=BBCODE):
    data = {
        'image_url': 'https://imx.to/i/x',
        'thumb_url': 'https://t.imx.to/t/x.jpg',
        'gallery_id': gallery_id,
        'bbcode': bbcode,
    }
    if gallery_name is not None:
        data['gallery_name'] = gallery_name
    return {'status': 'success', 'data': data}


def _make_mock_uploader():
    up = MagicMock()
    up.config = MagicMock()
    up.config.max_file_size_mb = None
    up.supports_gallery_rename.return_value = True
    up.sanitize_gallery_name.side_effect = lambda n: n
    up.get_gallery_url.return_value = "https://imx.to/g/test"
    up.get_thumbnail_url.return_value = "https://t.imx.to/t/test.jpg"
    up.fetch_batch_results.return_value = {}
    up.upload_image.side_effect = lambda *a, **k: _ok()
    return up


def _folder(tmp_path, names=('cover.jpg', '001.jpg', '002.jpg')):
    for n in names:
        (tmp_path / n).write_bytes(JPEG)
    return tmp_path


def _run(up, folder, **kwargs):
    engine = UploadEngine(up, rename_worker=MagicMock())
    params = dict(
        folder_path=str(folder),
        gallery_name="Test Gallery",
        thumbnail_size=3,
        thumbnail_format=2,
        max_retries=0,
        parallel_batch_size=1,
        template_name="default",
    )
    params.update(kwargs)
    return engine, engine.run(**params)


def _name(call):
    return os.path.basename(call.args[0])


def test_cover_creates_gallery_with_name_and_size_5(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'], cover_thumbnail_format=4)

    calls = up.upload_image.call_args_list
    first = calls[0]
    assert _name(first) == 'cover.jpg'
    assert first.kwargs['create_gallery'] and first.kwargs['thumbnail_size'] == 5
    assert first.kwargs['gallery_name'] == 'Test Gallery' and first.kwargs['thumbnail_format'] == 4
    assert [_name(c) for c in calls[1:]] == ['001.jpg', '002.jpg']
    assert all(c.kwargs.get('gallery_id') == 'gal1' for c in calls[1:])
    assert all(c.kwargs['thumbnail_size'] == 3 and c.kwargs['thumbnail_format'] == 2 for c in calls[1:])


def test_cover_result_shape_and_exclusion_from_counts(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'])

    assert result['cover_result'] == [{
        'status': 'success',
        'bbcode': BBCODE,
        'image_url': 'https://imx.to/i/x',
        'thumb_url': 'https://t.imx.to/t/x.jpg',
        'source_path': str(tmp_path / 'cover.jpg'),
    }]
    assert result['successful_count'] == 2 and result['total_images'] == 2
    assert result['failed_count'] == 0
    assert len(result['images']) == 2
    assert all(img['original_filename'] != 'cover.jpg' for img in result['images'])


def test_cover_progress_excludes_cover(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    progress = []
    _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'],
         on_progress=lambda done, total, pct, name: progress.append((done, total, name)))

    assert progress[0][0] == 0 and all(total == 2 for _, total, _ in progress)
    assert progress[-1][0] == 2
    assert all(name != 'cover.jpg' for _, _, name in progress)


def test_cover_that_named_the_gallery_queues_no_rename(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = (
        lambda *a, **k: _ok(gallery_name='Test Gallery') if k.get('create_gallery') else _ok()
    )
    engine, _ = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'])

    engine.rename_worker.queue_rename.assert_not_called()


def test_cover_that_created_unnamed_gallery_queues_rename(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    engine, _ = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'])

    engine.rename_worker.queue_rename.assert_called_once_with('gal1', 'Test Gallery')


def test_two_covers_second_joins_gallery(tmp_path):
    _folder(tmp_path, ('cover.jpg', 'cover2.jpg', '001.jpg'))
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg', 'cover2.jpg'],
                     exclude_cover_files=['cover.jpg', 'cover2.jpg'])

    calls = up.upload_image.call_args_list
    assert [_name(c) for c in calls] == ['cover.jpg', 'cover2.jpg', '001.jpg']
    second = calls[1]
    assert second.kwargs['gallery_id'] == 'gal1' and second.kwargs['thumbnail_size'] == 5
    assert not second.kwargs.get('create_gallery')
    assert [r['source_path'] for r in result['cover_result']] == [
        str(tmp_path / 'cover.jpg'), str(tmp_path / 'cover2.jpg')]


def test_also_upload_mode_uploads_cover_twice(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=None)

    cover_calls = [c for c in up.upload_image.call_args_list if _name(c) == 'cover.jpg']
    assert sorted(c.kwargs['thumbnail_size'] for c in cover_calls) == [3, 5]
    assert result['successful_count'] == 3 and result['total_images'] == 3
    assert len(result['cover_result']) == 1


def test_cover_failure_falls_through_to_regular_first_image(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()

    def fake(path, **kwargs):
        if os.path.basename(path) == 'cover.jpg':
            raise RuntimeError("boom")
        return _ok()

    up.upload_image.side_effect = fake
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'])

    assert result['cover_result'][0]['status'] == 'failed'
    assert 'boom' in result['cover_result'][0]['error']
    assert result['cover_result'][0]['source_path'] == str(tmp_path / 'cover.jpg')
    assert 'gallery_id' not in result['cover_result'][0]
    non_cover = [c for c in up.upload_image.call_args_list if _name(c) != 'cover.jpg']
    assert _name(non_cover[0]) == '001.jpg' and non_cover[0].kwargs['create_gallery'] is True
    assert result['successful_count'] == 2


def test_cover_api_error_is_recorded_with_message(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()

    def fake(path, **kwargs):
        if os.path.basename(path) == 'cover.jpg':
            return {'status': 'error', 'error': 'Invalid or inactive API key', 'data': {}}
        return _ok()

    up.upload_image.side_effect = fake
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'])

    assert result['cover_result'] == [{
        'status': 'failed', 'error': 'Invalid or inactive API key', 'source_path': str(tmp_path / 'cover.jpg')}]


def test_existing_gallery_covers_join_with_size_5(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'],
                     existing_gallery_id='old1')

    calls = up.upload_image.call_args_list
    assert _name(calls[0]) == 'cover.jpg'
    assert calls[0].kwargs['gallery_id'] == 'old1' and calls[0].kwargs['thumbnail_size'] == 5
    assert not calls[0].kwargs.get('create_gallery')
    assert all(c.kwargs['gallery_id'] == 'old1' for c in calls)
    assert result['cover_result'][0]['status'] == 'success'


def test_dedicated_cover_gallery_uploads_after_main_pass(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'],
                     cover_gallery_id='cov9')

    calls = up.upload_image.call_args_list
    assert [_name(c) for c in calls] == ['001.jpg', '002.jpg', 'cover.jpg']
    assert calls[0].kwargs['create_gallery'] is True
    last = calls[-1]
    assert last.kwargs['gallery_id'] == 'cov9' and last.kwargs['thumbnail_size'] == 5
    assert not last.kwargs.get('create_gallery')
    assert result['gallery_id'] == 'gal1'
    assert result['cover_result'][0]['status'] == 'success'


def test_cover_only_folder_still_creates_gallery(tmp_path):
    _folder(tmp_path, ('cover.jpg',))
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'])

    assert result['gallery_id'] == 'gal1'
    assert result['successful_count'] == 0 and result['total_images'] == 0
    assert result['cover_result'][0]['status'] == 'success'


def test_cover_only_folder_with_failing_cover_raises(tmp_path):
    _folder(tmp_path, ('cover.jpg',))
    up = _make_mock_uploader()
    up.upload_image.side_effect = lambda *a, **k: {'status': 'error', 'error': 'nope', 'data': {}}

    with pytest.raises(Exception, match='nope'):
        _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'])


def test_cover_outside_folder_is_uploaded_from_its_own_path(tmp_path):
    gallery = tmp_path / 'gallery'
    other = tmp_path / 'other'
    gallery.mkdir()
    other.mkdir()
    _folder(gallery, ('001.jpg', '002.jpg'))
    _folder(other, ('c.jpg',))
    cover = str(other / 'c.jpg')
    up = _make_mock_uploader()
    _, result = _run(up, gallery, cover_files=[cover])

    assert up.upload_image.call_args_list[0].args[0] == cover
    assert result['cover_result'][0]['source_path'] == cover
    assert result['successful_count'] == 2


def test_no_cover_files_leaves_results_unchanged(tmp_path):
    _folder(tmp_path, ('001.jpg', '002.jpg'))
    _, result = _run(_make_mock_uploader(), tmp_path)
    _, result_empty = _run(_make_mock_uploader(), tmp_path, cover_files=[])

    assert 'cover_result' not in result and 'cover_result' not in result_empty
    assert result['successful_count'] == 2


def test_empty_folder_without_covers_still_raises(tmp_path):
    with pytest.raises(ValueError, match='No image files'):
        _run(_make_mock_uploader(), tmp_path)


def test_soft_stop_skips_later_covers_without_raising(tmp_path):
    _folder(tmp_path, ('cover.jpg', 'cover2.jpg', '001.jpg'))
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg', 'cover2.jpg'],
                     exclude_cover_files=['cover.jpg', 'cover2.jpg'], should_soft_stop=lambda: True)

    assert [r['status'] for r in result['cover_result']] == ['success', 'failed']
    assert 'stopped' in result['cover_result'][1]['error']
    assert result['gallery_id'] == 'gal1'
    uploaded = [_name(c) for c in up.upload_image.call_args_list]
    assert uploaded[0] == 'cover.jpg' and 'cover2.jpg' not in uploaded


def test_soft_stop_skips_dedicated_gallery_covers(tmp_path):
    _folder(tmp_path)
    up = _make_mock_uploader()
    _, result = _run(up, tmp_path, cover_files=['cover.jpg'], exclude_cover_files=['cover.jpg'],
                     cover_gallery_id='cov9', should_soft_stop=lambda: True)

    assert result['cover_result'][0]['status'] == 'failed'
    assert 'cover.jpg' not in [_name(c) for c in up.upload_image.call_args_list]
    assert result['gallery_id'] == 'gal1'
