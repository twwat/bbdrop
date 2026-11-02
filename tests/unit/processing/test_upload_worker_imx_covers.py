# tests/unit/processing/test_upload_worker_imx_covers.py
"""Worker-side routing of IMX covers through the engine's cover pass."""
import os

import pytest
from unittest.mock import patch, MagicMock, Mock

from src.network.image_host_client import ImageHostClient
from src.storage.queue_manager import GalleryQueueItem

pytestmark = pytest.mark.unit


def _item(**kw):
    defaults = dict(
        path="/tmp/test",
        image_host_id="imx",
        cover_source_path="C:/g/cover.jpg;C:/g/cover2.jpg",
        cover_host_id="imx",
        cover_result=None,
    )
    defaults.update(kw)
    return GalleryQueueItem(**defaults)


def _mock_qsettings(values=None):
    store = {'cover/host_id': '', 'cover/exclude_from_gallery': False}
    store.update(values or {})
    settings = MagicMock()
    settings.value.side_effect = lambda key, default=None, **kw: store.get(key, default)
    return settings


def _host_setting(overrides=None):
    defaults = {'cover_gallery': '', 'cover_thumbnail_format': 2, 'cover_thumbnail_size': 600}
    defaults.update(overrides or {})
    return lambda host_id, key, value_type='str': defaults.get(key)


@pytest.fixture
def worker():
    from src.processing.upload_workers import UploadWorker
    w = UploadWorker(Mock())
    w.rename_worker = MagicMock()
    w.rename_worker.login_successful = True
    return w


class TestResolveCoverHost:
    def test_chain(self):
        from src.processing.upload_workers import resolve_cover_host
        assert resolve_cover_host(_item(cover_host_id="pixhost"), "turbo") == "pixhost"
        assert resolve_cover_host(_item(cover_host_id=None), "turbo") == "turbo"
        assert resolve_cover_host(_item(cover_host_id=None, image_host_id="pixhost"), "") == "pixhost"
        assert resolve_cover_host(_item(cover_host_id=None, image_host_id=None), "") == "imx"


class TestImxCoverPlan:
    def test_imx_cover_plan_returns_paths_for_imx_on_imx(self):
        from src.processing.upload_workers import imx_cover_plan
        assert imx_cover_plan(_item(), "imx", "") == (["C:/g/cover.jpg", "C:/g/cover2.jpg"], None)

    def test_imx_cover_plan_skips_already_successful(self):
        from src.processing.upload_workers import imx_cover_plan
        item = _item(cover_result=[{'status': 'success', 'source_path': 'C:\\g\\cover.jpg'}])
        assert imx_cover_plan(item, "imx", "") == (["C:/g/cover2.jpg"], None)

    def test_failed_earlier_cover_is_retried(self):
        from src.processing.upload_workers import imx_cover_plan
        item = _item(cover_result=[{'status': 'failed', 'source_path': 'C:/g/cover.jpg', 'error': 'x'}])
        assert imx_cover_plan(item, "imx", "")[0] == ["C:/g/cover.jpg", "C:/g/cover2.jpg"]

    def test_all_done_gives_empty_list(self):
        from src.processing.upload_workers import imx_cover_plan
        item = _item(cover_result=[
            {'status': 'success', 'source_path': 'C:\\g\\cover.jpg'},
            {'status': 'success', 'source_path': 'C:\\g\\cover2.jpg'},
        ])
        assert imx_cover_plan(item, "imx", "") == ([], None)

    @pytest.mark.parametrize("gallery_host,cover_host", [
        ("turbo", "turbo"), ("turbo", "imx"), ("pixhost", "pixhost"), ("imx", "turbo"), ("imx", "pixhost"),
    ])
    def test_imx_cover_plan_empty_for_other_hosts(self, gallery_host, cover_host):
        from src.processing.upload_workers import imx_cover_plan
        assert imx_cover_plan(_item(image_host_id=gallery_host), cover_host, "abc1") == ([], None)

    def test_imx_cover_plan_passes_dedicated_gallery(self):
        from src.processing.upload_workers import imx_cover_plan
        paths, gid = imx_cover_plan(_item(), "imx", "abc1")
        assert gid == "abc1"
        assert len(paths) == 2

    def test_no_cover_source_path(self):
        from src.processing.upload_workers import imx_cover_plan
        assert imx_cover_plan(_item(cover_source_path=None), "imx", "") == ([], None)
        assert imx_cover_plan(_item(cover_source_path=""), "imx", "x") == ([], None)

    def test_blank_segments_ignored(self):
        from src.processing.upload_workers import imx_cover_plan
        assert imx_cover_plan(_item(cover_source_path="C:/g/a.jpg; ;"), "imx", "")[0] == ["C:/g/a.jpg"]


class TestCoverStatusAndMerge:
    def test_cover_status_from_results(self):
        from src.processing.upload_workers import cover_status_from_results
        ok = {'status': 'success'}
        bad = {'status': 'failed'}
        assert cover_status_from_results([ok, ok]) == 'completed'
        assert cover_status_from_results([ok, bad]) == 'partial'
        assert cover_status_from_results([bad, bad]) == 'failed'
        assert cover_status_from_results([]) == 'failed'

    def test_merge_cover_results_replaces_same_source_path(self):
        from src.processing.upload_workers import merge_cover_results
        previous = [
            {'status': 'success', 'source_path': 'C:\\g\\a.jpg', 'bbcode': 'old-a'},
            {'status': 'failed', 'source_path': 'C:\\g\\b.jpg', 'error': 'x'},
        ]
        new = [
            {'status': 'success', 'source_path': 'C:/g/a.jpg', 'bbcode': 'new-a'},
            {'status': 'success', 'source_path': 'C:/g/b.jpg', 'bbcode': 'new-b'},
        ]
        merged = merge_cover_results(previous, new)
        assert [r['bbcode'] for r in merged] == ['new-a', 'new-b']

    def test_merge_keeps_previous_successes_not_in_new(self):
        from src.processing.upload_workers import merge_cover_results
        previous = [{'status': 'success', 'source_path': 'C:/g/a.jpg', 'bbcode': 'a'}]
        new = [{'status': 'failed', 'source_path': 'C:/g/b.jpg', 'error': 'x'}]
        merged = merge_cover_results(previous, new)
        assert merged == previous + new

    def test_merge_drops_previous_failures(self):
        from src.processing.upload_workers import merge_cover_results
        previous = [{'status': 'failed', 'source_path': 'C:/g/a.jpg', 'error': 'x'}]
        assert merge_cover_results(previous, []) == []

    def test_merge_with_no_previous(self):
        from src.processing.upload_workers import merge_cover_results
        new = [{'status': 'success', 'source_path': 'C:/g/a.jpg'}]
        assert merge_cover_results(None, new) == new


class TestUploadCoverRouting:
    def test_upload_cover_returns_none_for_imx(self, worker):
        done = [{'status': 'success', 'source_path': 'C:/g/cover.jpg', 'bbcode': 'a'},
                {'status': 'failed', 'source_path': 'C:/g/cover2.jpg', 'error': 'x'}]
        item = _item(image_host_id="imx", cover_host_id="imx", cover_result=list(done))
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting', side_effect=_host_setting()), \
             patch('src.processing.upload_workers.create_image_host_client') as factory:
            assert worker._upload_cover(item, gallery_id="gal") is None
        factory.assert_not_called()
        # Covers the engine already tried (even failed ones) are not repeated by the worker
        assert item.cover_result == done

    def test_turbo_gallery_imx_cover_uses_api_with_size_5(self, worker):
        item = _item(image_host_id="turbo", cover_host_id="imx", cover_source_path="/tmp/test/cover.jpg")
        client = MagicMock(spec=ImageHostClient)
        client.upload_image.return_value = {
            "status": "success",
            "data": {"image_url": "https://imx.to/i/1", "thumb_url": "https://imx.to/u/t/1.jpg",
                     "bbcode": "[URL=x][IMG]y[/IMG][/URL]"},
        }
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_host_setting({'cover_gallery': 'dedicated', 'cover_thumbnail_format': 3})), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=client) as factory:
            result = worker._upload_cover(item, gallery_id="turbo_gal")
        factory.assert_called_once_with('imx')
        client.upload_image.assert_called_once_with(
            "/tmp/test/cover.jpg", gallery_id="dedicated", thumbnail_size=5, thumbnail_format=3)
        assert result == [{
            'status': 'success', 'bbcode': "[URL=x][IMG]y[/IMG][/URL]",
            'image_url': "https://imx.to/i/1", 'thumb_url': "https://imx.to/u/t/1.jpg",
            'source_path': "/tmp/test/cover.jpg",
        }]
        assert item.cover_result == result
        assert item.cover_status == "completed"

    def test_non_imx_gallery_imx_cover_failure_recorded(self, worker):
        item = _item(image_host_id="turbo", cover_host_id="imx", cover_source_path="/tmp/test/cover.jpg")
        client = MagicMock(spec=ImageHostClient)
        client.upload_image.return_value = {"status": "error", "error": "boom"}
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting', side_effect=_host_setting()), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=client):
            result = worker._upload_cover(item, gallery_id="g")
        assert result == [{'status': 'failed', 'error': 'boom', 'source_path': '/tmp/test/cover.jpg'}]
        assert item.cover_status == "failed"

    def test_non_imx_gallery_imx_cover_exception_recorded(self, worker):
        item = _item(image_host_id="turbo", cover_host_id="imx", cover_source_path="/tmp/test/cover.jpg")
        client = MagicMock(spec=ImageHostClient)
        client.upload_image.side_effect = RuntimeError("net down")
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting', side_effect=_host_setting()), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=client):
            result = worker._upload_cover(item, gallery_id="g")
        assert result[0]['status'] == 'failed'
        assert 'net down' in result[0]['error']


class TestEngineCallSite:
    """_run_upload_engine hands IMX covers to the engine and keeps the stored results."""

    def _run(self, worker, item, engine_results, host_overrides=None, qvalues=None):
        engine = MagicMock()
        engine.run.return_value = engine_results
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings(qvalues)), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_host_setting(host_overrides)), \
             patch('src.processing.upload_workers.UploadEngine', return_value=engine), \
             patch.object(worker, '_restore_resume_state'), \
             patch.object(worker, '_merge_resume_results', side_effect=lambda i, r, f: dict(r)):
            worker.current_item = item
            results = worker._run_upload_engine(item, 3, 2, 3, 4)
        return engine, results

    def test_engine_gets_covers_format_and_gallery(self, worker):
        item = _item()
        new = [{'status': 'success', 'source_path': 'C:\\g\\cover.jpg', 'bbcode': 'a'},
               {'status': 'failed', 'source_path': 'C:\\g\\cover2.jpg', 'error': 'x'}]
        engine, results = self._run(
            worker, item, {'cover_result': new, 'images': []},
            host_overrides={'cover_thumbnail_format': 4, 'cover_gallery': 'ded1'})
        kwargs = engine.run.call_args.kwargs
        assert kwargs['cover_files'] == ["C:/g/cover.jpg", "C:/g/cover2.jpg"]
        assert kwargs['cover_thumbnail_format'] == 4
        assert kwargs['cover_gallery_id'] == 'ded1'
        assert item.cover_result == new
        assert item.cover_status == 'partial'
        assert results['cover_result'] == new

    def test_thumbnail_format_defaults_to_2(self, worker):
        item = _item()
        engine, _ = self._run(worker, item, {'cover_result': [], 'images': []},
                              host_overrides={'cover_thumbnail_format': 0})
        assert engine.run.call_args.kwargs['cover_thumbnail_format'] == 2

    def test_resume_merges_previous_successes(self, worker):
        item = _item(cover_result=[{'status': 'success', 'source_path': 'C:\\g\\cover.jpg', 'bbcode': 'old'}])
        new = [{'status': 'success', 'source_path': 'C:/g/cover2.jpg', 'bbcode': 'b'}]
        engine, results = self._run(worker, item, {'cover_result': new, 'images': []})
        assert engine.run.call_args.kwargs['cover_files'] == ["C:/g/cover2.jpg"]
        assert [r['bbcode'] for r in item.cover_result] == ['old', 'b']
        assert item.cover_status == 'completed'
        assert results['cover_result'] == item.cover_result

    def test_resume_with_all_covers_done_keeps_cover_result_in_results(self, worker):
        done = [{'status': 'success', 'source_path': 'C:\\g\\cover.jpg', 'bbcode': 'a'},
                {'status': 'success', 'source_path': 'C:\\g\\cover2.jpg', 'bbcode': 'b'}]
        item = _item(cover_result=list(done), cover_status="completed")
        engine, results = self._run(worker, item, {'images': []})
        assert engine.run.call_args.kwargs['cover_files'] is None
        assert results['cover_result'] == done
        assert item.cover_result == done
        assert item.cover_status == "completed"

    def test_turbo_gallery_never_gets_cover_files(self, worker):
        item = _item(image_host_id="turbo", cover_host_id="imx")
        engine, results = self._run(worker, item, {'images': []})
        kwargs = engine.run.call_args.kwargs
        assert kwargs['cover_files'] is None
        assert 'cover_result' not in results

    def test_imx_gallery_with_other_cover_host_never_gets_cover_files(self, worker):
        item = _item(image_host_id="imx", cover_host_id="pixhost")
        engine, results = self._run(worker, item, {'images': []})
        assert engine.run.call_args.kwargs['cover_files'] is None
        assert 'cover_result' not in results

    def test_session_cover_host_setting_is_honoured(self, worker):
        item = _item(cover_host_id=None)
        engine, _ = self._run(worker, item, {'images': []}, qvalues={'cover/host_id': 'pixhost'})
        assert engine.run.call_args.kwargs['cover_files'] is None

    def test_no_covers_leaves_call_untouched(self, worker):
        item = _item(cover_source_path=None)
        engine, results = self._run(worker, item, {'images': []})
        assert engine.run.call_args.kwargs['cover_files'] is None
        assert 'cover_result' not in results


class TestOrderAndVideo:
    def test_merge_follows_cover_path_order(self):
        from src.processing.upload_workers import merge_cover_results
        previous = [{'status': 'success', 'source_path': 'C:/g/b.jpg', 'bbcode': 'b'}]
        new = [{'status': 'success', 'source_path': 'C:/g/a.jpg', 'bbcode': 'a'}]
        # previous entries come first without ordering; the order list must put b before a
        merged = merge_cover_results(previous, new, order=['C:/g/b.jpg', 'C:/g/a.jpg'])
        assert [r['bbcode'] for r in merged] == ['b', 'a']
        merged = merge_cover_results(previous, new, order=['C:/g/a.jpg', 'C:/g/b.jpg'])
        assert [r['bbcode'] for r in merged] == ['a', 'b']

    def test_merge_order_matches_other_spellings_of_the_same_path(self):
        # The earlier success (listed FIRST in order) is spelled differently from the order entry.
        # Unmatched entries sort last, so without normalised matching this would give ['a', 'b'].
        from src.processing.upload_workers import merge_cover_results
        previous = [{'status': 'success', 'source_path': 'C:/g/./b.jpg', 'bbcode': 'b'}]
        new = [{'status': 'success', 'source_path': 'C:/g/a.jpg', 'bbcode': 'a'}]
        merged = merge_cover_results(previous, new, order=['C:/g/b.jpg', 'C:/g/a.jpg'])
        assert [r['bbcode'] for r in merged] == ['b', 'a']

    @pytest.mark.skipif(os.name != 'nt', reason='backslash and case folding are only equivalent on Windows')
    def test_merge_order_matches_backslash_and_case_spellings_on_windows(self):
        from src.processing.upload_workers import merge_cover_results
        bs = chr(92)
        previous = [{'status': 'success', 'source_path': 'C:' + bs + 'G' + bs + 'B.jpg', 'bbcode': 'b'}]
        new = [{'status': 'success', 'source_path': 'C:/g/a.jpg', 'bbcode': 'a'}]
        merged = merge_cover_results(previous, new, order=['C:/g/b.jpg', 'C:/g/a.jpg'])
        assert [r['bbcode'] for r in merged] == ['b', 'a']

    def test_video_item_on_imx_still_uploads_its_cover(self, worker):
        item = _item(media_type="video", cover_source_path="/tmp/test/cover.jpg")
        client = MagicMock(spec=ImageHostClient)
        client.upload_image.return_value = {
            "status": "success", "data": {"image_url": "i", "thumb_url": "t", "bbcode": "bb"}}
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting', side_effect=_host_setting()), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=client):
            result = worker._upload_cover(item, gallery_id="g")
        assert result[0]['status'] == 'success'
        client.upload_image.assert_called_once()


# --- helpers shared with the other cover test modules ---------------------------------

def api_response(flat):
    """Cover fields (status, bbcode, image_url, thumb_url) as the normalized upload_image response."""
    if flat is None or isinstance(flat, BaseException):
        return flat
    return {"status": flat["status"],
            "data": {k: flat[k] for k in ("bbcode", "image_url", "thumb_url") if k in flat}}


def imx_api_client(return_value=None, side_effect=None):
    """Mock IMX image host client; accepts flat cover dicts, None or exceptions."""
    client = MagicMock(spec=ImageHostClient)
    if side_effect is not None:
        if isinstance(side_effect, list):
            client.upload_image.side_effect = [api_response(x) for x in side_effect]
        else:
            client.upload_image.side_effect = side_effect
    else:
        client.upload_image.return_value = api_response(return_value)
    return client


def upload_cover_via(worker, item, client, gallery_id="gal123"):
    """Run worker._upload_cover with create_image_host_client returning ``client``."""
    with patch('src.processing.upload_workers.create_image_host_client', return_value=client):
        return worker._upload_cover(item, gallery_id=gallery_id)


class TestReplacedCoverAndDurability:
    def _run_with(self, worker, item, run_side_effect):
        engine = MagicMock()
        engine.run.side_effect = run_side_effect
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting', side_effect=_host_setting()), \
             patch('src.processing.upload_workers.UploadEngine', return_value=engine), \
             patch.object(worker, '_restore_resume_state'), \
             patch.object(worker, '_merge_resume_results', side_effect=lambda i, r, f: dict(r)):
            worker.current_item = item
            return engine, worker._run_upload_engine(item, 3, 2, 3, 4)

    def test_current_cover_results_drops_replaced_covers(self):
        from src.processing.upload_workers import current_cover_results
        item = _item(cover_source_path="C:/g/new.jpg", cover_result=[
            {'status': 'success', 'source_path': 'C:' + chr(92) + 'g' + chr(92) + 'old.jpg', 'bbcode': 'OLD'},
            {'status': 'success', 'source_path': 'C:' + chr(92) + 'g' + chr(92) + 'new.jpg', 'bbcode': 'NEW'},
        ])
        assert [r['bbcode'] for r in current_cover_results(item)] == ['NEW']
        assert current_cover_results(_item(cover_source_path=None, cover_result=item.cover_result)) == []

    def test_replaced_cover_is_uploaded_and_old_one_not_posted(self, worker):
        item = _item(cover_source_path="C:/g/new.jpg", cover_result=[
            {'status': 'success', 'source_path': 'C:/g/old.jpg', 'bbcode': 'OLD'}])
        new = [{'status': 'success', 'source_path': 'C:/g/new.jpg', 'bbcode': 'NEW'}]
        engine, results = self._run_with(worker, item, lambda **kw: {'cover_result': new, 'images': []})
        assert engine.run.call_args is not None
        assert [r['bbcode'] for r in item.cover_result] == ['NEW']
        assert [r['bbcode'] for r in results['cover_result']] == ['NEW']

    def test_replaced_cover_already_done_is_reattached_without_the_old_one(self, worker):
        item = _item(cover_source_path="C:/g/new.jpg", cover_result=[
            {'status': 'success', 'source_path': 'C:/g/old.jpg', 'bbcode': 'OLD'},
            {'status': 'success', 'source_path': 'C:/g/new.jpg', 'bbcode': 'NEW'}])
        engine, results = self._run_with(worker, item, lambda **kw: {'images': []})
        assert engine.run.call_args.kwargs['cover_files'] is None
        assert [r['bbcode'] for r in results['cover_result']] == ['NEW']

    def test_cover_is_on_the_item_and_in_the_database_while_run_is_going(self, worker):
        item = _item(cover_source_path="C:/g/cover.jpg")
        seen = {}
        cover = {'status': 'success', 'source_path': 'C:/g/cover.jpg', 'bbcode': 'B'}

        def fake_run(**kw):
            kw['on_cover_uploaded'](dict(cover))
            seen['during'] = list(item.cover_result or [])
            seen['status'] = item.cover_status
            seen['saved'] = worker.queue_manager.store.set_cover_result.call_args
            return {'cover_result': [dict(cover)], 'images': []}

        _, results = self._run_with(worker, item, fake_run)
        assert seen['during'] == [cover] and seen['status'] == 'completed'
        assert seen['saved'].args == ("/tmp/test", 'completed', [cover])
        # The final merge after run() is idempotent
        assert item.cover_result == [cover]
        assert results['cover_result'] == [cover]

    def test_cover_survives_run_raising_afterwards(self, worker):
        item = _item(cover_source_path="C:/g/cover.jpg")
        cover = {'status': 'success', 'source_path': 'C:/g/cover.jpg', 'bbcode': 'B'}

        def fake_run(**kw):
            kw['on_cover_uploaded'](dict(cover))
            raise RuntimeError("killed during the images")

        with pytest.raises(RuntimeError):
            self._run_with(worker, item, fake_run)
        assert item.cover_result == [cover]
        worker.queue_manager.store.set_cover_result.assert_called_once()

    def test_failing_database_write_does_not_break_the_callback(self, worker):
        item = _item(cover_source_path="C:/g/cover.jpg")
        worker.queue_manager.store.set_cover_result.side_effect = OSError("disk")
        cover = {'status': 'success', 'source_path': 'C:/g/cover.jpg', 'bbcode': 'B'}

        def fake_run(**kw):
            kw['on_cover_uploaded'](dict(cover))
            return {'images': []}

        _, results = self._run_with(worker, item, fake_run)
        assert item.cover_result == [cover]
        assert results['cover_result'] == [cover]


class TestLateImxCovers:
    """A cover set by the started hook or by Set cover during the upload is uploaded after the images."""

    def _call(self, worker, item, client, host_overrides=None, gallery_id="gal7"):
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_host_setting(host_overrides)), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=client) as factory:
            result = worker._upload_cover(item, gallery_id=gallery_id)
        return result, factory

    def test_unplanned_cover_is_uploaded_into_the_gallery(self, worker):
        item = _item(cover_source_path="C:/g/late.jpg", cover_result=None)
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'L', 'image_url': 'i', 'thumb_url': 't'})
        result, factory = self._call(worker, item, client, {'cover_thumbnail_format': 3})
        factory.assert_called_once_with('imx')
        client.upload_image.assert_called_once_with(
            "C:/g/late.jpg", gallery_id="gal7", thumbnail_size=5, thumbnail_format=3)
        assert [r['bbcode'] for r in result] == ['L']
        assert item.cover_result == result and item.cover_status == 'completed'
        worker.queue_manager.store.set_cover_result.assert_called_once()

    def test_dedicated_cover_gallery_wins(self, worker):
        item = _item(cover_source_path="C:/g/late.jpg")
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'L', 'image_url': 'i', 'thumb_url': 't'})
        self._call(worker, item, client, {'cover_gallery': 'ded1'})
        assert client.upload_image.call_args.kwargs['gallery_id'] == 'ded1'

    def test_only_the_missing_cover_is_uploaded_and_results_are_merged(self, worker):
        done = {'status': 'success', 'source_path': 'C:/g/cover.jpg', 'bbcode': 'A'}
        item = _item(cover_source_path="C:/g/cover.jpg;C:/g/late.jpg", cover_result=[dict(done)])
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'L', 'image_url': 'i', 'thumb_url': 't'})
        result, _ = self._call(worker, item, client)
        assert client.upload_image.call_count == 1
        assert [r['bbcode'] for r in result] == ['A', 'L']

    def test_a_cover_the_engine_already_failed_is_not_retried_straight_away(self, worker):
        failed = {'status': 'failed', 'source_path': 'C:/g/cover.jpg', 'error': 'x'}
        item = _item(cover_source_path="C:/g/cover.jpg", cover_result=[failed])
        client = imx_api_client(return_value=None)
        result, factory = self._call(worker, item, client)
        assert result is None
        factory.assert_not_called()

    def test_late_upload_failure_is_recorded(self, worker):
        item = _item(cover_source_path="C:/g/late.jpg")
        client = imx_api_client(side_effect=RuntimeError("net down"))
        result, _ = self._call(worker, item, client)
        assert result[0]['status'] == 'failed' and 'net down' in result[0]['error']
        assert item.cover_status == 'failed'

    def test_replaced_cover_result_is_not_kept(self, worker):
        old = {'status': 'success', 'source_path': 'C:/g/old.jpg', 'bbcode': 'OLD'}
        item = _item(cover_source_path="C:/g/new.jpg", cover_result=[old])
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'NEW', 'image_url': 'i', 'thumb_url': 't'})
        result, _ = self._call(worker, item, client)
        assert [r['bbcode'] for r in result] == ['NEW']

    def test_join_waits_for_the_started_hook_before_reading_the_path(self, worker):
        import threading
        import time
        item = _item(cover_source_path=None, cover_result=None)

        def hook():
            time.sleep(0.2)
            item.cover_source_path = "C:/g/hooked.jpg"

        worker._started_hook_thread = threading.Thread(target=hook, daemon=True)
        worker._started_hook_thread.start()
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'H', 'image_url': 'i', 'thumb_url': 't'})
        result, _ = self._call(worker, item, client)
        assert [r['bbcode'] for r in result] == ['H']


class TestEndToEndThroughEngine:
    """Real UploadEngine with a mocked uploader, driven through the worker's two entry points."""

    def _worker(self, item):
        from src.core.engine import AtomicCounter
        from src.processing.upload_workers import UploadWorker
        from tests.unit.core.test_engine_cover_first import _make_mock_uploader
        w = UploadWorker(Mock())
        w.rename_worker = MagicMock()
        w.uploader = _make_mock_uploader()
        w.current_item = item
        w.current_gallery_counter = AtomicCounter()
        w.queue_manager = MagicMock()
        w.queue_manager.store.get_uploaded_images.return_value = []
        w.gallery_completed = MagicMock()
        w.gallery_failed = MagicMock()
        w._emit_queue_stats = MagicMock()
        return w

    def _drive(self, worker, item, client):
        captured = {}

        def fake_save(it, results):
            captured['results'] = dict(results)
            return {}

        with patch('src.processing.upload_workers.QSettings',
                   return_value=_mock_qsettings({'cover/exclude_from_gallery': True})), \
             patch('src.processing.upload_workers.get_image_host_setting', side_effect=_host_setting()), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=client), \
             patch('src.utils.metrics_store.get_metrics_store', return_value=None), \
             patch.object(worker, '_save_artifacts_for_result', side_effect=fake_save), \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value={}):
            results = worker._run_upload_engine(item, 3, 2, 0, 1)
            worker._process_upload_results(item, results)
        return captured['results']

    def _folder(self, tmp_path):
        from tests.unit.core.test_engine_cover_first import _folder
        return _folder(tmp_path, names=('cover.jpg', 'late.jpg', '001.jpg', '002.jpg'))

    def test_cover_set_by_the_started_hook_during_the_upload_is_posted(self, tmp_path):
        import threading
        import time
        folder = self._folder(tmp_path)
        item = _item(path=str(folder), name="g", cover_source_path=None, cover_result=None)
        worker = self._worker(item)
        late = str(folder / 'late.jpg')

        def hook():
            time.sleep(0.2)
            item.cover_source_path = late

        worker._started_hook_thread = threading.Thread(target=hook, daemon=True)
        worker._started_hook_thread.start()
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'LATE', 'image_url': 'i', 'thumb_url': 't'})

        results = self._drive(worker, item, client)

        client.upload_image.assert_called_once()
        assert client.upload_image.call_args.args[0] == late
        assert client.upload_image.call_args.kwargs['gallery_id'] == 'gal1'
        assert [r['bbcode'] for r in results['cover_result']] == ['LATE']
        assert item.cover_status == 'completed'

    def test_known_cover_is_uploaded_once_by_the_engine_only(self, tmp_path):
        folder = self._folder(tmp_path)
        cover = str(folder / 'cover.jpg')
        item = _item(path=str(folder), name="g", cover_source_path=cover, cover_result=None)
        worker = self._worker(item)
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'X', 'image_url': 'i', 'thumb_url': 't'})

        results = self._drive(worker, item, client)

        client.upload_image.assert_not_called()
        engine_calls = [c for c in worker.uploader.upload_image.call_args_list
                        if c.args[0].endswith('cover.jpg')]
        assert len(engine_calls) == 1
        assert len(results['cover_result']) == 1 and results['cover_result'][0]['status'] == 'success'

    def test_known_and_late_covers_both_end_up_in_the_post(self, tmp_path):
        folder = self._folder(tmp_path)
        cover, late = str(folder / 'cover.jpg'), str(folder / 'late.jpg')
        item = _item(path=str(folder), name="g", cover_source_path=cover, cover_result=None)
        worker = self._worker(item)
        client = imx_api_client(return_value={'status': 'success', 'bbcode': 'LATE', 'image_url': 'i', 'thumb_url': 't'})
        # Set cover adds a second cover while the engine is running
        original_run = worker.uploader.upload_image.side_effect

        def upload(*a, **k):
            if a[0].endswith('001.jpg'):
                item.cover_source_path = cover + ';' + late
            return original_run(*a, **k)

        worker.uploader.upload_image.side_effect = upload

        results = self._drive(worker, item, client)

        assert [os.path.basename(r['source_path']) for r in results['cover_result']] == ['cover.jpg', 'late.jpg']
        client.upload_image.assert_called_once()
