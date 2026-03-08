# tests/unit/processing/test_cover_full_flow.py
"""Integration test: cover detection -> upload -> template output."""

from unittest.mock import patch, MagicMock, Mock

from src.storage.queue_manager import GalleryQueueItem


class TestCoverFullFlow:
    """End-to-end cover photo flow with mocked network."""

    def test_cover_detection_to_template(self):
        """Cover detected during scan -> uploaded -> appears in #cover# placeholder."""
        # 1. Detection
        from src.core.cover_detector import detect_cover
        files = ["image001.jpg", "cover.jpg", "image002.jpg"]
        cover = detect_cover(files, patterns="cover*")
        assert cover == "cover.jpg"

        # 2. Set on item
        item = GalleryQueueItem(
            path="/tmp/test",
            name="Test Gallery",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        # 3. Simulate cover upload result
        item.cover_result = {
            "status": "success",
            "bbcode": "[url=https://imx.to/i/abc][img]https://t.imx.to/t/abc.jpg[/img][/url]",
            "image_url": "https://imx.to/i/abc",
            "thumb_url": "https://t.imx.to/t/abc.jpg",
        }

        # 4. Template resolution
        from src.utils.templates import apply_template
        template = "#cover#\n[b]#folderName#[/b]\n#allImages#"
        data = {
            'cover': item.cover_result.get('bbcode', ''),
            'folder_name': 'Test Gallery',
            'all_images': '[img]thumb1[/img]  [img]thumb2[/img]',
            'picture_count': 2,
        }
        result = apply_template(template, data)

        assert "[url=https://imx.to/i/abc]" in result
        assert "[b]Test Gallery[/b]" in result
        assert "[img]thumb1[/img]" in result

    def test_no_cover_template_empty(self):
        """When no cover is detected, #cover# resolves to empty string."""
        from src.utils.templates import apply_template
        template = "#cover#[b]#folderName#[/b]"
        data = {
            'cover': '',
            'folder_name': 'Test Gallery',
            'all_images': '',
            'picture_count': 0,
        }
        result = apply_template(template, data)
        assert result.startswith("[b]Test Gallery[/b]")

    def test_cover_conditional_with_content(self):
        """[if cover]...[/if] shows content when cover exists."""
        from src.utils.templates import apply_template
        template = "[if cover]#cover#[/if]\n#folderName#"

        # With cover
        data_with = {'cover': '[img]x[/img]', 'folder_name': 'Test', 'all_images': '', 'picture_count': 1}
        result_with = apply_template(template, data_with)
        assert "[img]x[/img]" in result_with

        # Without cover
        data_without = {'cover': '', 'folder_name': 'Test', 'all_images': '', 'picture_count': 1}
        result_without = apply_template(template, data_without)
        assert "[img]x[/img]" not in result_without
        assert "Test" in result_without

    def test_cover_data_model_roundtrip(self):
        """Cover fields survive creation -> dict -> item roundtrip."""
        item = GalleryQueueItem(
            path="/tmp/test",
            name="Test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
            cover_result={"bbcode": "x", "image_url": "y", "thumb_url": "z"},
        )
        assert item.cover_source_path == "/tmp/test/cover.jpg"
        assert item.cover_host_id == "imx"
        assert item.cover_result["bbcode"] == "x"

    def test_cover_detection_patterns(self):
        """Various cover detection patterns work correctly."""
        from src.core.cover_detector import detect_cover

        # Standard cover filename
        assert detect_cover(["img1.jpg", "cover.jpg"], patterns="cover*") == "cover.jpg"
        # Poster pattern
        assert detect_cover(["img1.jpg", "poster.png"], patterns="cover*, poster*") == "poster.png"
        # Suffix pattern
        assert detect_cover(["img1.jpg", "gallery_cover.jpg"], patterns="*_cover.*") == "gallery_cover.jpg"
        # No match
        assert detect_cover(["img1.jpg", "img2.jpg"], patterns="cover*") is None
        # Empty patterns
        assert detect_cover(["cover.jpg"], patterns="") is None


class TestFullCoverFlowGalleryCompletion:
    """Gallery completion status must be independent of cover upload outcome."""

    @patch('src.processing.upload_workers.RenameWorker')
    def test_full_cover_flow_gallery_completes_despite_cover_failure(self, mock_rw_class):
        """Gallery should be 'completed' even when cover upload fails.
        cover_status should be 'failed'. Progress shows gallery-only counts."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        # Cover upload fails: all paths return None
        worker.rename_worker.upload_cover.return_value = None
        worker.queue_manager = MagicMock()
        worker.gallery_completed = MagicMock()
        worker.gallery_failed = MagicMock()
        worker._soft_stop_requested_for = None
        worker._emit_queue_stats = MagicMock()

        # Item has 40 files total: 38 gallery + 2 covers
        item = GalleryQueueItem(
            path="/tmp/gallery40",
            name="gallery40",
            cover_source_path="/tmp/gallery40/cover1.jpg;/tmp/gallery40/cover2.jpg",
            cover_host_id="imx",
            image_host_id="imx",
        )
        item.start_time = 1000.0
        item.uploaded_bytes = 0

        # Simulate engine result: 38 gallery images all succeeded
        results = {
            'successful_count': 38,
            'total_images': 38,
            'failed_count': 0,
            'gallery_id': 'g123',
            'gallery_url': 'https://imx.to/g/g123',
            'gallery_name': 'gallery40',
        }

        with patch('src.utils.metrics_store.get_metrics_store', return_value=None), \
             patch.object(worker, '_save_artifacts_for_result', return_value={}), \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value={}):
            worker._process_upload_results(item, results)

        # Gallery should be marked completed (38/38 success) despite cover failure
        worker.queue_manager.update_item_status.assert_called_with(
            "/tmp/gallery40", "completed"
        )

        # Cover status should be 'failed' because both covers returned None
        assert item.cover_status == "failed"

        # results dict should NOT have inflated total_images
        assert results['total_images'] == 38
        assert results['successful_count'] == 38

        # gallery_completed signal should still have been emitted
        worker.gallery_completed.emit.assert_called_once_with("/tmp/gallery40", results)

    @patch('src.processing.upload_workers.RenameWorker')
    def test_full_cover_flow_bbcode_populated_on_success(self, mock_rw_class):
        """#cover# placeholder should be populated when covers upload successfully."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True

        cover_data_1 = {
            "status": "success",
            "bbcode": "[url=https://imx.to/i/aaa][img]https://t.imx.to/t/aaa.jpg[/img][/url]",
            "image_url": "https://imx.to/i/aaa",
            "thumb_url": "https://t.imx.to/t/aaa.jpg",
        }
        cover_data_2 = {
            "status": "success",
            "bbcode": "[url=https://imx.to/i/bbb][img]https://t.imx.to/t/bbb.jpg[/img][/url]",
            "image_url": "https://imx.to/i/bbb",
            "thumb_url": "https://t.imx.to/t/bbb.jpg",
        }
        worker.rename_worker.upload_cover.side_effect = [cover_data_1, cover_data_2]

        item = GalleryQueueItem(
            path="/tmp/gallery_covers",
            name="gallery_covers",
            cover_source_path="/tmp/gallery_covers/cover1.jpg;/tmp/gallery_covers/cover2.jpg",
            cover_host_id="imx",
        )

        # Step 1: Call _upload_cover directly
        result = worker._upload_cover(item, gallery_id="gal_abc")

        # Must return a list of 2 success dicts
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["status"] == "success"
        assert result[1]["status"] == "success"

        # Each result should have its source_path attached
        assert result[0]["source_path"] == "/tmp/gallery_covers/cover1.jpg"
        assert result[1]["source_path"] == "/tmp/gallery_covers/cover2.jpg"

        # item.cover_result should be stored as a list
        assert isinstance(item.cover_result, list)
        assert len(item.cover_result) == 2

        # item.cover_status should be "completed" (all succeeded)
        assert item.cover_status == "completed"

        # Step 2: Verify cover_bbcode can be built correctly from results
        # This mirrors the logic in _save_artifacts_for_result (line 696-699)
        cover_bbcode = "\n".join(
            r['bbcode'] for r in (item.cover_result or [])
            if r.get('status') == 'success' and r.get('bbcode')
        )
        assert "[url=https://imx.to/i/aaa]" in cover_bbcode
        assert "[url=https://imx.to/i/bbb]" in cover_bbcode
        # Both bbcodes should be newline-separated
        assert cover_bbcode.count("\n") == 1

        # Step 3: Verify cover_url extraction (first successful image_url)
        cover_url = next(
            (r.get('image_url', '') for r in (item.cover_result or [])
             if r.get('status') == 'success'),
            ''
        )
        assert cover_url == "https://imx.to/i/aaa"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_full_cover_flow_partial_cover_success(self, mock_rw_class):
        """When 1 of 2 covers succeeds, cover_status='partial', bbcode has successful one."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True

        # First cover succeeds, second fails with exception
        cover_success = {
            "status": "success",
            "bbcode": "[url=https://imx.to/i/ok1][img]https://t.imx.to/t/ok1.jpg[/img][/url]",
            "image_url": "https://imx.to/i/ok1",
            "thumb_url": "https://t.imx.to/t/ok1.jpg",
        }
        worker.rename_worker.upload_cover.side_effect = [
            cover_success,
            RuntimeError("server 500"),
        ]

        item = GalleryQueueItem(
            path="/tmp/gallery_partial",
            name="gallery_partial",
            cover_source_path="/tmp/gallery_partial/cover1.jpg;/tmp/gallery_partial/cover2.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal_partial")

        # Should return list with 2 entries
        assert isinstance(result, list)
        assert len(result) == 2

        # First entry: success with source_path
        assert result[0]['status'] == 'success'
        assert result[0]['source_path'] == '/tmp/gallery_partial/cover1.jpg'
        assert 'bbcode' in result[0]
        assert result[0]['bbcode'] == cover_success['bbcode']

        # Second entry: failed with error and source_path
        assert result[1]['status'] == 'failed'
        assert result[1]['source_path'] == '/tmp/gallery_partial/cover2.jpg'
        assert 'server 500' in result[1]['error']

        # item.cover_status should be "partial"
        assert item.cover_status == "partial"

        # item.cover_result stored as list
        assert isinstance(item.cover_result, list)
        assert len(item.cover_result) == 2

        # cover_bbcode should include ONLY the successful cover, not the failed one
        cover_bbcode = "\n".join(
            r['bbcode'] for r in (item.cover_result or [])
            if r.get('status') == 'success' and r.get('bbcode')
        )
        assert "[url=https://imx.to/i/ok1]" in cover_bbcode
        # Should NOT contain any reference to the failed cover
        assert "server 500" not in cover_bbcode
        # Only one bbcode line (no newline separator since only 1 success)
        assert "\n" not in cover_bbcode

        # cover_url should be the first successful image_url
        cover_url = next(
            (r.get('image_url', '') for r in (item.cover_result or [])
             if r.get('status') == 'success'),
            ''
        )
        assert cover_url == "https://imx.to/i/ok1"

        # Verify this integrates with _process_upload_results correctly:
        # gallery still completes, cover failure doesn't block it
        worker.queue_manager = MagicMock()
        worker.gallery_completed = MagicMock()
        worker.gallery_failed = MagicMock()
        worker._soft_stop_requested_for = None
        worker._emit_queue_stats = MagicMock()

        item.start_time = 1000.0
        item.uploaded_bytes = 0

        engine_results = {
            'successful_count': 20,
            'total_images': 20,
            'failed_count': 0,
            'gallery_id': 'g_partial',
            'gallery_url': 'https://imx.to/g/g_partial',
            'gallery_name': 'gallery_partial',
        }

        # Reset upload_cover to simulate partial again for _process_upload_results
        worker.rename_worker.upload_cover.side_effect = [
            cover_success,
            RuntimeError("server 500"),
        ]

        with patch('src.utils.metrics_store.get_metrics_store', return_value=None), \
             patch.object(worker, '_save_artifacts_for_result', return_value={}), \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value={}):
            worker._process_upload_results(item, engine_results)

        # Gallery status: completed (20/20 gallery images succeeded)
        worker.queue_manager.update_item_status.assert_called_with(
            "/tmp/gallery_partial", "completed"
        )
        # Cover status: partial (1 of 2 succeeded)
        assert item.cover_status == "partial"
        # Engine total_images NOT inflated by cover count
        assert engine_results['total_images'] == 20
