"""Unit tests for FiledotFileManagerClient (web-scraping client)."""

from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

import pytest

from src.network.file_manager.filedot_client import FiledotFileManagerClient

# ---------------------------------------------------------------------------
# Fake HTTP client — no network, records all calls
# ---------------------------------------------------------------------------

class FakeFileHostClient:
    def __init__(self, responses: Dict[str, bytes]):
        # responses: url-prefix -> body bytes
        self.responses = responses
        self.calls: List[Tuple[str, str, Dict]] = []  # (method, url, kwargs)

    def request(
        self,
        method,
        url,
        *,
        headers=None,
        body=None,
        follow_redirects=True,
        count_bandwidth=True,
        timeout=60,
    ):
        self.calls.append((method, url, {"headers": headers, "body": body, "timeout": timeout}))
        for prefix, resp in self.responses.items():
            if url.startswith(prefix):
                return 200, {}, resp
        return 404, {}, b""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_sample_html() -> bytes:
    """Return the bytes of the saved Filedot file-listing page, or skip."""
    path = pathlib.Path(__file__).parents[4] / "logs" / "filedot.to-files.htm"
    if not path.exists():
        pytest.skip(f"Sample HTML not found at {path}")
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_filedot_parses_user_sample_html():
    """FiledotFileManagerClient correctly parses the real saved HTML page."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({"https://filedot.to/files/": html_bytes})
    client = FiledotFileManagerClient(fake)

    result = client.list_files("/")

    folders = [f for f in result.files if f.is_folder]
    files = [f for f in result.files if not f.is_folder]

    assert len(folders) == 17, f"Expected 17 folders, got {len(folders)}"
    assert len(files) == 500, f"Expected 500 files, got {len(files)}"
    assert client._action_token == "a8ea1b794ae9b74e79471c0a98e8d2fa", (
        f"Token mismatch: {client._action_token!r}"
    )

    # list_files returns folders first then files
    first_file = files[0]
    assert first_file.name, "First file should have a non-empty name"
    assert first_file.id, "First file should have a non-empty id (file code)"
    assert first_file.size > 0, "First file should have a positive size"
    assert not first_file.is_folder


def test_filedot_navigate_into_subfolder_builds_correct_url():
    """list_files('14264') should request the URL with fld_id=14264&page=1."""
    fake = FakeFileHostClient({"https://filedot.to/files/": b"<html></html>"})
    client = FiledotFileManagerClient(fake)

    client.list_files("14264")

    assert len(fake.calls) == 1
    method, url, _ = fake.calls[0]
    assert method == "GET"
    assert url == "https://filedot.to/files/?fld_id=14264&page=1"


def test_filedot_scrape_caches_numeric_ids_and_folders():
    """_scrape_page populates file_code→numeric_id map and folder-id set."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({"https://filedot.to/files/": html_bytes})
    client = FiledotFileManagerClient(fake)

    client.list_files("/")

    assert len(client._file_code_to_numeric) == 500
    assert len(client._known_folder_ids) == 17

    # First file in the fixture: file_code 7qz9r9pkumql ↔ numeric 1487377
    assert client._file_code_to_numeric["7qz9r9pkumql"] == "1487377"

    # Known folders from the action panel fixture
    assert "14264" in client._known_folder_ids  # BoppinBabes
    assert "14475" in client._known_folder_ids  # UpskirtJerk

    # Folder-id tracking for the fld_id form field
    assert client._last_folder_id == "/"
    assert client._last_list_fld_id == "0"


def test_filedot_scrape_resets_caches_per_folder():
    """Scraping a second folder clears the caches from the previous scrape."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/files/?fld_id=14264": b"<html></html>",
    })
    client = FiledotFileManagerClient(fake)

    client.list_files("/")
    assert len(client._file_code_to_numeric) == 500
    assert "14264" in client._known_folder_ids

    client.list_files("14264")
    assert client._file_code_to_numeric == {}
    assert client._known_folder_ids == set()
    assert client._last_folder_id == "14264"
    assert client._last_list_fld_id == "14264"


def test_filedot_create_folder_posts_main_form():
    """create_folder POSTs the main action form with create_folder_submit."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")  # prime token + fld_id caches

    result = client.create_folder("NewDir", "/", "public")

    assert result.success is True
    post_calls = [c for c in fake.calls if c[0] == "POST"]
    assert len(post_calls) == 1
    method, url, kwargs = post_calls[0]
    assert url == "https://filedot.to/"
    body = kwargs["body"].decode("utf-8")
    assert "op=my_files" in body
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in body
    assert "fld_id=0" in body
    assert "create_new_folder=NewDir" in body
    assert "create_folder_submit=Create" in body  # "Create Folder" url-encoded


def test_filedot_create_folder_in_subfolder():
    """create_folder with a numeric parent_id sends fld_id=<parent>."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.create_folder("Sub", "14264", "public")

    assert result.success is True
    body = [c for c in fake.calls if c[0] == "POST"][0][2]["body"].decode()
    assert "fld_id=14264" in body
    assert "create_new_folder=Sub" in body


def test_filedot_move_posts_numeric_ids_and_to_folder_move():
    """move POSTs the action form with repeated file_id= and to_folder_move."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.move(
        ["7qz9r9pkumql", "ouldtymewaiq"],  # first two files in fixture
        "14264",
    )

    assert result.all_succeeded
    assert set(result.succeeded) == {"7qz9r9pkumql", "ouldtymewaiq"}

    post = [c for c in fake.calls if c[0] == "POST"][0]
    url = post[1]
    body = post[2]["body"].decode("utf-8")
    assert url == "https://filedot.to/"
    assert "op=my_files" in body
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in body
    assert "fld_id=0" in body
    assert "to_folder=14264" in body
    assert "to_folder_move=Move+files" in body
    # Numeric file_ids appear as repeated file_id= params
    assert body.count("file_id=") == 2
    assert "file_id=1487377" in body  # 7qz9r9pkumql → 1487377
    assert "file_id=1487376" in body  # ouldtymewaiq → 1487376


def test_filedot_copy_uses_to_folder_copy():
    """copy shares move's shape but sends to_folder_copy instead."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.copy(["7qz9r9pkumql"], "14264")

    assert result.all_succeeded
    body = [c for c in fake.calls if c[0] == "POST"][0][2]["body"].decode()
    assert "to_folder_copy=Copy+files" in body
    assert "to_folder_move" not in body
    assert "file_id=1487377" in body


def test_filedot_delete_folder_uses_del_folder_url():
    """delete on a known folder id issues GET with del_folder= and token."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/files?fld_id=0": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.delete(["14264"])  # known folder from fixture

    assert result.all_succeeded
    assert "14264" in result.succeeded

    del_calls = [
        (m, u) for m, u, _ in fake.calls
        if "del_folder" in u
    ]
    assert len(del_calls) == 1
    _method, url = del_calls[0]
    assert "del_folder=14264" in url
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in url
    assert "fld_id=0" in url


def test_filedot_delete_mixed_files_and_folders():
    """delete handles a list containing both a file_code and a folder id."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/files?del_code=": b"<html>ok</html>",
        "https://filedot.to/files?fld_id=0": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.delete(["7qz9r9pkumql", "14264"])

    assert result.all_succeeded
    assert set(result.succeeded) == {"7qz9r9pkumql", "14264"}

    urls = [u for m, u, _ in fake.calls if m == "GET" and "token" in u]
    # One del_code url for the file, one del_folder url for the folder
    assert any("del_code=7qz9r9pkumql" in u for u in urls)
    assert any("del_folder=14264" in u for u in urls)


def test_filedot_set_file_public_publishes_via_set_flag():
    """set_file_public(True) POSTs op=my_files&set_flag=file_public&value=1."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/?": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.set_file_public(["7qz9r9pkumql"], True)

    assert result.all_succeeded
    post = [c for c in fake.calls if c[0] == "POST"][0]
    url = post[1]
    body = post[2]["body"].decode("utf-8")
    assert url == "https://filedot.to/?"
    assert "op=my_files" in body
    assert "set_flag=file_public" in body
    assert "value=1" in body
    assert "file_id=1487377" in body
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in body


def test_filedot_set_file_public_unpublishes_with_value_zero():
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/?": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.set_file_public(["7qz9r9pkumql"], False)

    assert result.all_succeeded
    body = [c for c in fake.calls if c[0] == "POST"][0][2]["body"].decode()
    assert "value=0" in body


def test_filedot_set_file_premium_uses_premium_only_flag():
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/?": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.set_file_premium(["7qz9r9pkumql"], True)

    assert result.all_succeeded
    body = [c for c in fake.calls if c[0] == "POST"][0][2]["body"].decode()
    assert "set_flag=file_premium_only" in body
    assert "value=1" in body
    assert "file_id=1487377" in body


def test_filedot_set_flag_repeats_file_id_for_multiple():
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/?": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.set_file_public(["7qz9r9pkumql", "ouldtymewaiq"], True)

    assert result.all_succeeded
    body = [c for c in fake.calls if c[0] == "POST"][0][2]["body"].decode()
    assert body.count("file_id=") == 2
    assert "file_id=1487377" in body
    assert "file_id=1487376" in body


def test_filedot_set_flag_reports_stale_token():
    """If the response contains a stale-token marker, all items fail."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/?": b"<html>Anti-CSRF check failed</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.set_file_public(["7qz9r9pkumql"], True)

    assert not result.all_succeeded
    assert not result.succeeded
    assert any("CSRF" in msg for _, msg in result.failed)
    # Token should have been cleared so next op re-primes
    assert client._action_token == ""


def _load_file_edit_fixture() -> bytes:
    path = (
        pathlib.Path(__file__).parent / "fixtures" / "filedot_file_edit.htm"
    )
    return path.read_bytes()


def test_filedot_rename_folder_posts_fld_edit():
    """rename of a known folder id POSTs /fld_edit with fld_name."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/fld_edit": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.rename("14264", "BoppinBabes Renamed")

    assert result.success
    post = [c for c in fake.calls if c[0] == "POST"][0]
    assert post[1] == "https://filedot.to/fld_edit?fld_id=14264"
    body = post[2]["body"].decode("utf-8")
    assert "op=fld_edit" in body
    assert "fld_id=14264" in body
    assert "fld_name=BoppinBabes+Renamed" in body
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in body
    assert "save=Save" in body


def test_filedot_rename_file_posts_file_edit():
    """rename of a file_code POSTs /file_edit with file_name."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/file_edit": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.rename("7qz9r9pkumql", "new_name.zip")

    assert result.success
    post = [c for c in fake.calls if c[0] == "POST"][0]
    assert post[1] == "https://filedot.to/file_edit?file_code=7qz9r9pkumql"
    body = post[2]["body"].decode("utf-8")
    assert "op=file_edit" in body
    assert "file_code=7qz9r9pkumql" in body
    assert "file_name=new_name.zip" in body
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in body


def test_filedot_read_file_properties_parses_fixture():
    """read_file_properties extracts fields from the /file_edit form."""
    list_html = _load_sample_html()
    edit_html = _load_file_edit_fixture()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": list_html,
        "https://filedot.to/file_edit?file_code=7qz9r9pkumql": edit_html,
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    props = client.read_file_properties("7qz9r9pkumql")

    assert props["file_name"] == "Original File.zip"
    assert props["file_descr"] == "Old description text"
    assert props["file_password"] == "oldpw"
    assert props["file_price"] == "2.50"
    assert props["file_public"] == "1"  # checked in fixture
    assert props["file_premium_only"] == "0"  # not checked


def test_filedot_update_properties_single_file_round_trips():
    """Single-file path: GET the form, merge fields, POST full form back."""
    list_html = _load_sample_html()
    edit_html = _load_file_edit_fixture()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": list_html,
        "https://filedot.to/file_edit?file_code=7qz9r9pkumql": edit_html,
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.update_file_properties(
        ["7qz9r9pkumql"],
        {"file_descr": "new desc", "file_price": "5.00"},
        round_trip=True,
    )

    assert result.all_succeeded

    # Expect exactly one GET (priming) and one POST
    gets = [c for c in fake.calls if c[0] == "GET" and "file_edit" in c[1]]
    posts = [c for c in fake.calls if c[0] == "POST" and "file_edit" in c[1]]
    assert len(gets) == 1
    assert len(posts) == 1

    body = posts[0][2]["body"].decode("utf-8")
    # Overrides applied
    assert "file_descr=new+desc" in body
    assert "file_price=5.00" in body
    # Untouched fields preserved from the fixture
    assert "file_name=Original+File.zip" in body
    assert "file_password=oldpw" in body
    assert "file_public=1" in body
    assert "file_premium_only=0" in body
    # Mandatory POST fields
    assert "op=file_edit" in body
    assert "file_code=7qz9r9pkumql" in body
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in body
    assert "save=Save" in body


def test_filedot_update_properties_multi_file_skips_round_trip():
    """Multi-file path: no GETs, one POST per file_code with diff only."""
    list_html = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": list_html,
        "https://filedot.to/file_edit": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.update_file_properties(
        ["7qz9r9pkumql", "ouldtymewaiq", "q385vkxff9su"],
        {"file_public": "1", "file_price": "9.99"},
        round_trip=False,
    )

    assert result.all_succeeded
    assert len(result.succeeded) == 3

    # Zero GETs to /file_edit (no round-trip)
    gets = [c for c in fake.calls if c[0] == "GET" and "file_edit" in c[1]]
    assert gets == []

    # Three POSTs, one per file_code
    posts = [c for c in fake.calls if c[0] == "POST" and "file_edit" in c[1]]
    assert len(posts) == 3

    for post in posts:
        body = post[2]["body"].decode("utf-8")
        # Only diffed fields present
        assert "file_public=1" in body
        assert "file_price=9.99" in body
        # Preserved fields NOT present (no round-trip)
        assert "file_descr" not in body
        assert "file_password" not in body
        # file_name is stripped in multi mode
        assert "file_name" not in body
        assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in body


def test_filedot_update_properties_multi_strips_file_name():
    """Multi-file path ignores file_name even if a caller passes it in."""
    list_html = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": list_html,
        "https://filedot.to/file_edit": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.update_file_properties(
        ["7qz9r9pkumql", "ouldtymewaiq"],
        {"file_name": "will_be_ignored", "file_descr": "batch"},
        round_trip=False,
    )

    assert result.all_succeeded
    for post in [c for c in fake.calls if c[0] == "POST" and "file_edit" in c[1]]:
        body = post[2]["body"].decode("utf-8")
        assert "file_name" not in body
        assert "file_descr=batch" in body


def test_filedot_update_properties_multi_aborts_on_stale_token():
    """Mid-loop stale-token response fails the current file AND skips the rest.

    Regression for M1: previously the loop kept POSTing with an empty
    token, silently marking later files as succeeded.
    """
    list_html = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": list_html,
        "https://filedot.to/file_edit": b"<html>Anti-CSRF check failed</html>",
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")

    result = client.update_file_properties(
        ["7qz9r9pkumql", "ouldtymewaiq", "q385vkxff9su"],
        {"file_public": "1"},
        round_trip=False,
    )

    assert not result.all_succeeded
    assert result.succeeded == []
    failed_codes = [c for c, _ in result.failed]
    assert set(failed_codes) == {
        "7qz9r9pkumql", "ouldtymewaiq", "q385vkxff9su",
    }
    # First failure is the rotation; the rest are skipped
    assert result.failed[0] == ("7qz9r9pkumql", "CSRF token rotated")
    assert all(
        "skipped" in msg for _, msg in result.failed[1:]
    )
    # Only ONE POST should have been made — the loop aborts on first rotation
    posts = [c for c in fake.calls if c[0] == "POST" and "file_edit" in c[1]]
    assert len(posts) == 1
    # Token was cleared so the next op re-primes
    assert client._action_token == ""


def test_filedot_read_file_properties_refreshes_token_from_form():
    """Regression for M2: read_file_properties picks up the per-form token."""
    list_html = _load_sample_html()
    edit_html = _load_file_edit_fixture()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": list_html,
        "https://filedot.to/file_edit?file_code=7qz9r9pkumql": edit_html,
    })
    client = FiledotFileManagerClient(fake)
    client.list_files("/")
    # Simulate the session token drifting before the Properties dialog opens
    client._action_token = "deadbeefdeadbeef" * 2

    client.read_file_properties("7qz9r9pkumql")

    # The fixture's hidden token input should have overwritten the stale value
    assert client._action_token == "a8ea1b794ae9b74e79471c0a98e8d2fa"


def test_filedot_delete_uses_cached_token():
    """delete() should use the token scraped by the preceding list_files call."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/files?del_code=": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)

    # Prime the token cache
    client.list_files("/")
    assert client._action_token == "a8ea1b794ae9b74e79471c0a98e8d2fa"

    result = client.delete(["clsl0fz7pfhl"])

    assert "clsl0fz7pfhl" in result.succeeded
    assert not result.failed

    # Find the delete call in the recorded calls
    delete_calls = [
        (m, u) for m, u, _ in fake.calls
        if "del_code" in u
    ]
    assert len(delete_calls) == 1, "Expected exactly one delete request"
    _method, delete_url = delete_calls[0]
    assert "del_code=clsl0fz7pfhl" in delete_url
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in delete_url
