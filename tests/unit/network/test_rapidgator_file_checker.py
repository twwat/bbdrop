"""Tests for RapidgatorFileChecker — file availability via check_link API."""

import pytest
import json
from unittest.mock import patch, MagicMock

from src.network.rapidgator_file_checker import RapidgatorFileChecker


@pytest.fixture
def checker():
    return RapidgatorFileChecker(auth_token='test-token')


class TestRapidgatorFileCheckerBasic:
    @patch.object(RapidgatorFileChecker, '_api_call')
    def test_all_available(self, mock_api, checker):
        mock_api.return_value = {
            "response": [
                {"url": "https://rapidgator.net/file/abc/a.zip", "filename": "a.zip", "status": "ACCESS", "size": 1000},
                {"url": "https://rapidgator.net/file/def/b.zip", "filename": "b.zip", "status": "ACCESS", "size": 2000},
            ],
            "status": 200,
        }
        urls = ["https://rapidgator.net/file/abc/a.zip", "https://rapidgator.net/file/def/b.zip"]
        result = checker.check_urls(urls)
        assert result["https://rapidgator.net/file/abc/a.zip"] == True
        assert result["https://rapidgator.net/file/def/b.zip"] == True

    @patch.object(RapidgatorFileChecker, '_api_call')
    def test_unavailable_file(self, mock_api, checker):
        mock_api.return_value = {
            "response": [
                {"url": "https://rapidgator.net/file/abc/a.zip", "status": "NO ACCESS"},
            ],
            "status": 200,
        }
        result = checker.check_urls(["https://rapidgator.net/file/abc/a.zip"])
        assert result["https://rapidgator.net/file/abc/a.zip"] == False

    def test_empty_urls_returns_empty(self, checker):
        result = checker.check_urls([])
        assert result == {}


class TestRapidgatorFileCheckerBatching:
    @patch.object(RapidgatorFileChecker, '_api_call')
    def test_batch_splits_at_25(self, mock_api, checker):
        mock_api.return_value = {
            "response": [{"url": f"https://rg.to/file/{i}", "status": "ACCESS"} for i in range(25)],
            "status": 200,
        }
        urls = [f"https://rg.to/file/{i}" for i in range(60)]
        checker.check_urls(urls)
        assert mock_api.call_count == 3  # 25 + 25 + 10

    @patch.object(RapidgatorFileChecker, '_api_call')
    def test_under_25_single_call(self, mock_api, checker):
        mock_api.return_value = {
            "response": [{"url": "u", "status": "ACCESS"}],
            "status": 200,
        }
        checker.check_urls(["https://rg.to/file/1"])
        assert mock_api.call_count == 1


class TestRapidgatorFileCheckerErrorHandling:
    @patch.object(RapidgatorFileChecker, '_api_call')
    def test_api_error_returns_none(self, mock_api, checker):
        mock_api.side_effect = Exception("timeout")
        result = checker.check_urls(["https://rg.to/file/abc"])
        assert result["https://rg.to/file/abc"] is None


class TestRapidgatorGalleryCheck:
    @patch.object(RapidgatorFileChecker, 'check_urls')
    def test_aggregates_results(self, mock_check, checker):
        mock_check.return_value = {
            'https://rg.to/file/1': True,
            'https://rg.to/file/2': False,
        }
        result = checker.check_gallery(['https://rg.to/file/1', 'https://rg.to/file/2'])
        assert result['status'] == 'partial'
        assert result['online'] == 1
        assert result['offline'] == 1
        assert result['total'] == 2
