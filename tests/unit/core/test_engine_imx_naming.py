"""Engine names the gallery in the request that creates it and skips the rename when that worked."""
from unittest.mock import MagicMock

import pytest

from src.core.engine import UploadEngine

pytestmark = pytest.mark.unit


def _ok(gallery_name=None):
    data = {
        'image_url': 'https://imx.to/i/test',
        'thumb_url': 'https://t.imx.to/t/test.jpg',
        'gallery_id': 'gal1',
        'original_filename': 'img.jpg',
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
    up.upload_image.return_value = _ok()
    return up


def _make_images(tmp_path, count=2):
    for i in range(count):
        (tmp_path / f"image{i + 1:03d}.jpg").write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)


def _run(engine, folder, name="Test Gallery"):
    return engine.run(
        folder_path=str(folder),
        gallery_name=name,
        thumbnail_size=6,
        thumbnail_format=2,
        max_retries=0,
        parallel_batch_size=1,
        template_name="default",
    )


def _engine(uploader):
    return UploadEngine(uploader, rename_worker=MagicMock())


def test_first_upload_carries_gallery_name(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    _run(_engine(up), tmp_path)

    first_kwargs = up.upload_image.call_args_list[0].kwargs
    assert first_kwargs['create_gallery'] is True
    assert first_kwargs['gallery_name'] == 'Test Gallery'


def test_no_rename_queued_when_response_has_gallery_name(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [_ok('Test Gallery'), _ok()]
    engine = _engine(up)
    _run(engine, tmp_path)

    engine.rename_worker.queue_rename.assert_not_called()


def test_rename_queued_when_response_lacks_gallery_name(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    engine = _engine(up)
    _run(engine, tmp_path)

    engine.rename_worker.queue_rename.assert_called_once_with('gal1', 'Test Gallery')


def test_invalid_name_retries_unnamed_then_queues_rename(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [
        {'status': 'error', 'error': 'Invalid gallery_name', 'data': {}},
        _ok(),
        _ok(),
    ]
    engine = _engine(up)
    result = _run(engine, tmp_path)

    first, second = up.upload_image.call_args_list[0], up.upload_image.call_args_list[1]
    assert first.kwargs['gallery_name'] == 'Test Gallery'
    assert second.kwargs['gallery_name'] is None
    assert second.kwargs['create_gallery'] is True
    assert result['gallery_id'] == 'gal1'
    engine.rename_worker.queue_rename.assert_called_once_with('gal1', 'Test Gallery')


def test_invalid_name_error_without_data_still_retries(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [
        {'status': 'error', 'error': 'Invalid GALLERY_NAME supplied'},
        _ok(),
        _ok(),
    ]
    result = _run(_engine(up), tmp_path)

    assert up.upload_image.call_args_list[1].kwargs['gallery_name'] is None
    assert result['gallery_id'] == 'gal1'


def test_other_error_on_create_is_not_retried(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [
        {'status': 'error', 'error': 'Invalid or inactive API key', 'data': {}},
    ]
    with pytest.raises(Exception, match='Invalid or inactive API key'):
        _run(_engine(up), tmp_path)
    assert up.upload_image.call_count == 1


def test_untitled_name_from_disallowed_folder_still_uploads(tmp_path):
    folder = tmp_path / "\u2665\u2665\u2665"
    folder.mkdir()
    _make_images(folder)
    up = _make_mock_uploader()
    up.sanitize_gallery_name.side_effect = lambda n: 'untitled'
    engine = _engine(up)
    result = engine.run(
        folder_path=str(folder),
        gallery_name=None,
        thumbnail_size=6,
        thumbnail_format=2,
        max_retries=0,
        parallel_batch_size=1,
        template_name="default",
    )

    assert up.upload_image.call_args_list[0].kwargs['gallery_name'] == 'untitled'
    assert result['gallery_id'] == 'gal1'


def test_retry_response_with_default_name_still_queues_rename(tmp_path):
    """After the unnamed retry the API reports 'untitled gallery'; that is not a name we chose."""
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [
        {'status': 'error', 'error': 'Invalid gallery_name', 'data': {}},
        _ok(gallery_name='untitled gallery'),
        _ok(),
    ]
    engine = _engine(up)
    _run(engine, tmp_path)

    engine.rename_worker.queue_rename.assert_called_once_with('gal1', 'Test Gallery')


def test_create_helper_no_name_sent_is_not_named(tmp_path):
    img = tmp_path / 'a.jpg'
    img.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 10)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [_ok(gallery_name='untitled gallery')]
    response, named = _engine(up)._create_gallery_with(str(img), None, 6, 2, None)
    assert named is False
    assert response['status'] == 'success'


def test_invalid_name_raised_as_exception_retries_unnamed(tmp_path):
    """The client raises on any non-200 response; the name rejection must still retry."""
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [
        Exception("Upload failed with status code 400: Invalid gallery_name"),
        _ok(gallery_name='untitled gallery'),
        _ok(),
    ]
    engine = _engine(up)
    result = _run(engine, tmp_path)

    assert up.upload_image.call_args_list[0].kwargs['gallery_name'] == 'Test Gallery'
    assert up.upload_image.call_args_list[1].kwargs['gallery_name'] is None
    assert result['gallery_id'] == 'gal1'
    engine.rename_worker.queue_rename.assert_called_once_with('gal1', 'Test Gallery')


def test_name_exception_check_is_case_insensitive(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [Exception("bad GALLERY_NAME"), _ok(), _ok()]
    result = _run(_engine(up), tmp_path)
    assert result['gallery_id'] == 'gal1'


def test_other_exception_on_create_propagates_unchanged(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = Exception("Upload failed with status code 401: Invalid or inactive API key")
    with pytest.raises(Exception, match='Invalid or inactive API key'):
        _run(_engine(up), tmp_path)
    assert up.upload_image.call_count == 1


def test_name_exception_is_not_retried_when_no_name_was_sent(tmp_path):
    img = tmp_path / 'a.jpg'
    img.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 10)
    up = _make_mock_uploader()
    up.upload_image.side_effect = Exception("Invalid gallery_name")
    with pytest.raises(Exception, match='gallery_name'):
        _engine(up)._create_gallery_with(str(img), None, 6, 2, None)
    assert up.upload_image.call_count == 1


def test_failed_create_message_has_no_dict(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [{'status': 'error', 'error': 'Invalid or inactive API key', 'data': {}}]
    with pytest.raises(Exception) as excinfo:
        _run(_engine(up), tmp_path)
    text = str(excinfo.value)
    assert text == 'Failed to create gallery: Invalid or inactive API key'
    assert '{' not in text


def test_failed_create_without_message_has_no_dict(tmp_path):
    _make_images(tmp_path)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [{'status': 'error', 'data': {}}]
    with pytest.raises(Exception) as excinfo:
        _run(_engine(up), tmp_path)
    assert '{' not in str(excinfo.value)
    assert 'Failed to create gallery' in str(excinfo.value)


def test_per_image_failure_reason_has_no_dict(tmp_path):
    _make_images(tmp_path, count=2)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [
        _ok(),
        {'status': 'error', 'error': 'File too large', 'data': {}},
    ]
    result = _run(_engine(up), tmp_path)

    reasons = [reason for _name, reason in result['failed_details']]
    assert reasons == ['API error: File too large']


def test_per_image_failure_without_message_has_no_dict(tmp_path):
    _make_images(tmp_path, count=2)
    up = _make_mock_uploader()
    up.upload_image.side_effect = [_ok(), {'status': 'error', 'data': {}}]
    result = _run(_engine(up), tmp_path)
    assert all('{' not in reason for _n, reason in result['failed_details'])
