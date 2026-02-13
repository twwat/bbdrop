import pytest
from src.processing.hook_output_parser import detect_stdout_values, resolve_placeholder


class TestDetectURLs:
    def test_single_url(self):
        result = detect_stdout_values("https://example.com/path/file.zip")
        urls = [v for v in result if v['type'] == 'url']
        assert len(urls) == 1
        assert urls[0]['value'] == "https://example.com/path/file.zip"
        assert urls[0]['index'] == 1

    def test_multiple_urls(self):
        text = "https://first.com/a.zip\nhttps://second.com/b.zip"
        result = detect_stdout_values(text)
        urls = [v for v in result if v['type'] == 'url']
        assert len(urls) == 2
        assert urls[0]['index'] == 1
        assert urls[1]['index'] == 2

    def test_url_does_not_produce_duplicate_path(self):
        """Bug: '//example.com/path/file.zip' was detected as a file path"""
        result = detect_stdout_values("https://example.com/path/file.zip")
        paths = [v for v in result if v['type'] == 'path']
        assert len(paths) == 0

    def test_url_does_not_produce_kv_match(self):
        """Bug: 'https' was detected as a key with value '//example.com/...'"""
        result = detect_stdout_values("https://example.com/path/file.zip")
        kvs = [v for v in result if v['type'] == 'data']
        assert len(kvs) == 0

    def test_ftp_url(self):
        result = detect_stdout_values("ftp://files.example.com/pub/data.tar.gz")
        urls = [v for v in result if v['type'] == 'url']
        assert len(urls) == 1
        assert urls[0]['value'] == "ftp://files.example.com/pub/data.tar.gz"

    def test_url_with_trailing_punctuation_stripped(self):
        result = detect_stdout_values("Download from https://example.com/file.zip.")
        urls = [v for v in result if v['type'] == 'url']
        assert len(urls) == 1
        assert urls[0]['value'] == "https://example.com/file.zip"


class TestDetectPaths:
    def test_windows_path(self):
        result = detect_stdout_values(r"C:\example\test.jpg")
        paths = [v for v in result if v['type'] == 'path']
        assert len(paths) == 1
        assert paths[0]['value'] == r"C:\example\test.jpg"

    def test_windows_path_no_drive_letter_key(self):
        """Bug: 'C' was detected as a key from 'C:\\example'"""
        result = detect_stdout_values(r"C:\example\test.jpg")
        kvs = [v for v in result if v['type'] == 'data']
        assert len(kvs) == 0

    def test_unix_path(self):
        result = detect_stdout_values("/home/user/file.txt")
        paths = [v for v in result if v['type'] == 'path']
        assert len(paths) == 1
        assert paths[0]['value'] == "/home/user/file.txt"

    def test_unix_path_not_detected_inside_url(self):
        """Paths that are substrings of URLs should not be detected"""
        result = detect_stdout_values("https://example.com/uploads/file.txt")
        paths = [v for v in result if v['type'] == 'path']
        assert len(paths) == 0

    def test_path_without_extension_skipped(self):
        """Bare directory names without extensions are not matched"""
        result = detect_stdout_values("/tmp/outputdir")
        paths = [v for v in result if v['type'] == 'path']
        # 'outputdir' has no extension and no trailing slash
        assert len(paths) == 0

    def test_path_with_trailing_slash_kept(self):
        result = detect_stdout_values("/tmp/output/")
        paths = [v for v in result if v['type'] == 'path']
        assert len(paths) == 1


class TestDetectKeyValues:
    def test_key_equals_value(self):
        result = detect_stdout_values("file_id=abc123")
        kvs = [v for v in result if v['type'] == 'data']
        assert len(kvs) == 1
        assert kvs[0]['key'] == 'file_id'
        assert kvs[0]['value'] == 'abc123'

    def test_key_colon_value(self):
        result = detect_stdout_values("status: success")
        kvs = [v for v in result if v['type'] == 'data']
        assert len(kvs) == 1
        assert kvs[0]['key'] == 'status'
        assert kvs[0]['value'] == 'success'

    def test_drive_letter_not_treated_as_key(self):
        """Single char before :\\ must not be treated as kv pair"""
        result = detect_stdout_values(r"C:\Users\test.jpg")
        kvs = [v for v in result if v['type'] == 'data']
        assert len(kvs) == 0

    def test_multiple_kvs(self):
        text = "id=123\nstatus=ok\nname=test"
        result = detect_stdout_values(text)
        kvs = [v for v in result if v['type'] == 'data']
        assert len(kvs) == 3


class TestDeduplication:
    def test_no_duplicates_from_url(self):
        """Same value should not appear twice under different types"""
        result = detect_stdout_values("https://example.com/file.zip")
        assert len(result) == 1

    def test_mixed_output(self):
        text = "https://example.com/file.zip\nC:\\Users\\test.jpg\nstatus=ok"
        result = detect_stdout_values(text)
        assert len(result) == 3
        types = {v['type'] for v in result}
        assert types == {'url', 'path', 'data'}


class TestNegativeIndexing:
    def test_positive_indices_assigned(self):
        text = "https://first.com/a\nhttps://second.com/b\nhttps://third.com/c"
        result = detect_stdout_values(text)
        urls = [v for v in result if v['type'] == 'url']
        assert len(urls) == 3
        assert urls[0]['index'] == 1
        assert urls[1]['index'] == 2
        assert urls[2]['index'] == 3


class TestResolvePlaceholder:
    def _urls(self):
        return detect_stdout_values(
            "https://example.com/uploads/photo.jpg\nhttps://mirror.org/files/backup.zip"
        )

    def _paths(self):
        return detect_stdout_values(
            r"C:\Users\me\photo.jpg" + "\n" + "/home/user/docs/report.pdf"
        )

    def test_url_1(self):
        assert resolve_placeholder("URL[1]", self._urls()) == "https://example.com/uploads/photo.jpg"

    def test_url_2(self):
        assert resolve_placeholder("URL[2]", self._urls()) == "https://mirror.org/files/backup.zip"

    def test_url_negative_1(self):
        assert resolve_placeholder("URL[-1]", self._urls()) == "https://mirror.org/files/backup.zip"

    def test_url_out_of_range(self):
        assert resolve_placeholder("URL[5]", self._urls()) == ""

    def test_url_zero_index(self):
        assert resolve_placeholder("URL[0]", self._urls()) == ""

    def test_url_domain(self):
        assert resolve_placeholder("URL[1].domain", self._urls()) == "example.com"

    def test_url_filename(self):
        assert resolve_placeholder("URL[1].filename", self._urls()) == "photo.jpg"

    def test_url_path(self):
        assert resolve_placeholder("URL[1].path", self._urls()) == "/uploads/photo.jpg"

    def test_url_extension(self):
        assert resolve_placeholder("URL[1].extension", self._urls()) == ".jpg"

    def test_url_ext_shorthand(self):
        assert resolve_placeholder("URL[1].ext", self._urls()) == ".jpg"

    def test_url_stem(self):
        assert resolve_placeholder("URL[1].stem", self._urls()) == "photo"

    def test_path_1(self):
        assert resolve_placeholder("PATH[1]", self._paths()) == r"C:\Users\me\photo.jpg"

    def test_path_filename(self):
        assert resolve_placeholder("PATH[1].filename", self._paths()) == "photo.jpg"

    def test_path_dir_windows(self):
        assert resolve_placeholder("PATH[1].dir", self._paths()) == r"C:\Users\me"

    def test_path_extension(self):
        assert resolve_placeholder("PATH[2].extension", self._paths()) == ".pdf"

    def test_path_stem(self):
        assert resolve_placeholder("PATH[2].stem", self._paths()) == "report"

    def test_case_insensitive(self):
        assert resolve_placeholder("url[1]", self._urls()) == "https://example.com/uploads/photo.jpg"

    def test_plain_json_key_returns_empty(self):
        """JSON key names should return empty (handled by separate logic)"""
        assert resolve_placeholder("download_url", self._urls()) == ""

    def test_no_matches_returns_empty(self):
        assert resolve_placeholder("URL[1]", []) == ""

    def test_path_negative_index(self):
        assert resolve_placeholder("PATH[-1]", self._paths()) == "/home/user/docs/report.pdf"
