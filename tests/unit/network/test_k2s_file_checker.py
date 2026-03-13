"""Tests for K2SFileChecker — file availability via getFilesList API."""

import pytest
from unittest.mock import patch, Mock

from src.network.k2s_file_checker import K2SFileChecker


@pytest.fixture
def checker():
    return K2SFileChecker(
        api_base='https://k2s.cc/api/v2',
        auth_token='test-token-123',
    )


class TestK2SFileCheckerBasic:
    @patch.object(K2SFileChecker, '_api_call')
    def test_all_available(self, mock_api, checker):
        mock_api.return_value = {
            "files": [
                {"id": "abc123", "is_available": True, "name": "archive.zip"},
                {"id": "def456", "is_available": True, "name": "archive2.zip"},
            ]
        }
        result = checker.check_files(["abc123", "def456"])
        assert result['abc123'] == True
        assert result['def456'] == True

    def test_empty_file_ids_returns_empty(self, checker):
        result = checker.check_files([])
        assert result == {}

    def test_api_base_normalization(self):
        c = K2SFileChecker(api_base='https://k2s.cc/api/v2/', auth_token='tok')
        assert not c.api_base.endswith('/')


class TestK2SFileCheckerBatching:
    def test_batch_size_default(self, checker):
        assert checker.batch_size == 10000

    @patch.object(K2SFileChecker, '_api_call')
    def test_single_batch_under_limit(self, mock_api, checker):
        mock_api.return_value = {
            "files": [{"id": f"id{i}", "is_available": True} for i in range(50)]
        }
        checker.check_files([f"id{i}" for i in range(50)])
        assert mock_api.call_count == 1

    @patch.object(K2SFileChecker, '_api_call')
    def test_multiple_batches_over_limit(self, mock_api, checker):
        checker.batch_size = 10
        mock_api.return_value = {
            "files": [{"id": f"id{i}", "is_available": True} for i in range(10)]
        }
        file_ids = [f"id{i}" for i in range(25)]
        checker.check_files(file_ids)
        assert mock_api.call_count == 3


class TestK2SFileCheckerErrorHandling:
    @patch.object(K2SFileChecker, '_api_call')
    def test_api_error_returns_none_values(self, mock_api, checker):
        mock_api.side_effect = Exception("API down")
        result = checker.check_files(["abc123"])
        assert result['abc123'] is None

    @patch.object(K2SFileChecker, '_api_call')
    def test_missing_file_in_response(self, mock_api, checker):
        mock_api.return_value = {
            "files": [{"id": "abc123", "is_available": True}]
        }
        result = checker.check_files(["abc123", "missing999"])
        assert result['abc123'] == True
        assert result['missing999'] is None


class TestK2SFileCheckerGalleryCheck:
    @patch.object(K2SFileChecker, 'check_files')
    def test_check_gallery_aggregates(self, mock_check, checker):
        mock_check.return_value = {'f1': True, 'f2': True, 'f3': False}
        result = checker.check_gallery({'f1': 'http://k2s.cc/file/f1', 'f2': 'http://k2s.cc/file/f2', 'f3': 'http://k2s.cc/file/f3'})
        assert result['online'] == 2
        assert result['offline'] == 1
        assert result['total'] == 3
        assert result['status'] == 'partial'

    @patch.object(K2SFileChecker, 'check_files')
    def test_check_gallery_all_online(self, mock_check, checker):
        mock_check.return_value = {'f1': True}
        result = checker.check_gallery({'f1': 'http://k2s.cc/file/f1'})
        assert result['status'] == 'online'
