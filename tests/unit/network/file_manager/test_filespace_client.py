"""Unit tests for FilespaceFileManagerClient (web-scraping subclass)."""

from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

import pytest

from src.network.file_manager.filespace_client import FilespaceFileManagerClient


class FakeFileHostClient:
    """Fake FileHostClient used by every filespace test — no network."""

    def __init__(self, responses: Dict[str, bytes]):
        self.responses = responses
        self.calls: List[Tuple[str, str, Dict]] = []

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
        self.calls.append(
            (method, url, {"headers": headers, "body": body, "timeout": timeout})
        )
        for prefix, resp in self.responses.items():
            if url.startswith(prefix):
                return 200, {}, resp
        return 404, {}, b""


FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load_my_files() -> bytes:
    path = FIXTURE_DIR / "filespace_my_files.htm"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return path.read_bytes()


def _load_file_edit() -> bytes:
    path = FIXTURE_DIR / "filespace_file_edit.htm"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return path.read_bytes()


# ---------------------------------------------------------------------------
# list_files / _scrape_page
# ---------------------------------------------------------------------------

def test_filespace_parses_fixture_root_page():
    """list_files('/') parses the fixture into 1 folder + 11 files."""
    html = _load_my_files()
    fake = FakeFileHostClient({"https://filespace.com/": html})
    client = FilespaceFileManagerClient(fake)

    result = client.list_files("/")
    folders = [f for f in result.files if f.is_folder]
    files = [f for f in result.files if not f.is_folder]

    assert len(folders) == 1, f"Expected 1 folder, got {len(folders)}"
    assert folders[0].id == "33018"
    assert folders[0].name == "subfolder test"

    assert len(files) == 11, f"Expected 11 files, got {len(files)}"
    codes = {f.id for f in files}
    assert "3zm41fbivvgp" in codes
    assert "i7off4ja4vio" in codes

    first = next(f for f in files if f.id == "3zm41fbivvgp")
    assert first.name == "Test114b.zip"
    assert first.size > 0

    # numeric id cache populated
    assert client._file_code_to_numeric["3zm41fbivvgp"] == "7265936"
    assert client._file_code_to_numeric["i7off4ja4vio"] == "7265934"
    assert client._known_folder_ids == {"33018"}


def test_filespace_list_root_builds_correct_url():
    """list_files('/') issues GET to /?op=my_files&fld_id=0&page=1."""
    fake = FakeFileHostClient({"https://filespace.com/": b"<html></html>"})
    client = FilespaceFileManagerClient(fake)

    client.list_files("/")

    assert len(fake.calls) == 1
    method, url, _ = fake.calls[0]
    assert method == "GET"
    assert url == "https://filespace.com/?op=my_files&fld_id=0&page=1"


def test_filespace_list_subfolder_builds_correct_url():
    """list_files('33018') issues GET with fld_id=33018."""
    fake = FakeFileHostClient({"https://filespace.com/": b"<html></html>"})
    client = FilespaceFileManagerClient(fake)

    client.list_files("33018")

    method, url, _ = fake.calls[0]
    assert url == "https://filespace.com/?op=my_files&fld_id=33018&page=1"


# ---------------------------------------------------------------------------
# create_folder
# ---------------------------------------------------------------------------

def test_filespace_create_folder_posts_action_form():
    """create_folder POSTs the main action form with create_folder_submit."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files": html,
        "https://filespace.com/": b"<html>ok</html>",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    result = client.create_folder("NewDir", "/", "public")

    assert result.success is True
    post = [c for c in fake.calls if c[0] == "POST"][0]
    assert post[1] == "https://filespace.com/"
    body = post[2]["body"].decode("utf-8")
    assert "op=my_files" in body
    assert "fld_id=0" in body
    assert "create_new_folder=NewDir" in body
    assert "create_folder_submit=Create" in body  # "Create Folder" url-encoded
    # Filespace has no CSRF token — confirm it is NOT in the body.
    assert "token=" not in body


def test_filespace_create_folder_in_subfolder():
    """create_folder with numeric parent_id sends fld_id=<parent>."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files": html,
        "https://filespace.com/": b"<html>ok</html>",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    client.create_folder("Sub", "33018", "public")

    body = [c for c in fake.calls if c[0] == "POST"][0][2]["body"].decode()
    assert "fld_id=33018" in body


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

def test_filespace_rename_file_posts_file_edit():
    """rename on a file_code POSTs to /?op=file_edit with file_name."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files": html,
        "https://filespace.com/?op=file_edit": b"<html>ok</html>",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    result = client.rename("3zm41fbivvgp", "NewName.zip")

    assert result.success is True
    post = [c for c in fake.calls if c[0] == "POST"][0]
    assert post[1] == "https://filespace.com/?op=file_edit&file_code=3zm41fbivvgp"
    body = post[2]["body"].decode("utf-8")
    assert "file_name=NewName.zip" in body
    assert "file_code=3zm41fbivvgp" in body
    assert "token=" not in body


def test_filespace_rename_folder_posts_fld_edit():
    """rename on a known folder id POSTs to /?op=fld_edit with fld_name."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files": html,
        "https://filespace.com/?op=fld_edit": b"<html>ok</html>",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    result = client.rename("33018", "renamed folder")

    assert result.success is True
    post = [c for c in fake.calls if c[0] == "POST"][0]
    assert post[1] == "https://filespace.com/?op=fld_edit&fld_id=33018"
    body = post[2]["body"].decode("utf-8")
    assert "fld_name=renamed+folder" in body
    assert "fld_id=33018" in body


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_filespace_delete_file_sends_del_code_get():
    """delete on a file_code issues GET to /?op=my_files&del_code=X."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files&fld_id=0": html,
        "https://filespace.com/?op=my_files&del_code=": b"ok",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    result = client.delete(["3zm41fbivvgp"])

    assert result.succeeded == ["3zm41fbivvgp"]
    delete_calls = [
        c for c in fake.calls if "del_code=3zm41fbivvgp" in c[1]
    ]
    assert len(delete_calls) == 1
    assert delete_calls[0][0] == "GET"
    assert "token=" not in delete_calls[0][1]


def test_filespace_delete_folder_sends_del_folder_get():
    """delete on a known folder id issues GET to /?op=my_files&fld_id=0&del_folder=X."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files&fld_id=0": html,
        "https://filespace.com/?op=my_files&fld_id=0&del_folder=": b"ok",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    result = client.delete(["33018"])

    assert result.succeeded == ["33018"]
    delete_calls = [c for c in fake.calls if "del_folder=33018" in c[1]]
    assert len(delete_calls) == 1
    assert delete_calls[0][0] == "GET"


# ---------------------------------------------------------------------------
# move / copy
# ---------------------------------------------------------------------------

def test_filespace_move_posts_numeric_ids_and_to_folder_move():
    """move POSTs action form with repeated file_id= and to_folder_move."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files": html,
        "https://filespace.com/": b"<html>ok</html>",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    result = client.move(["3zm41fbivvgp", "i7off4ja4vio"], "33018")

    assert result.all_succeeded
    assert set(result.succeeded) == {"3zm41fbivvgp", "i7off4ja4vio"}

    post = [c for c in fake.calls if c[0] == "POST"][0]
    assert post[1] == "https://filespace.com/"
    body = post[2]["body"].decode("utf-8")
    assert "op=my_files" in body
    assert "to_folder=33018" in body
    assert "to_folder_move=Move+files" in body
    assert body.count("file_id=7265936") == 1
    assert body.count("file_id=7265934") == 1
    assert "token=" not in body


def test_filespace_copy_posts_to_folder_copy():
    """copy uses to_folder_copy field instead of to_folder_move."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files": html,
        "https://filespace.com/": b"<html>ok</html>",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    client.copy(["3zm41fbivvgp"], "33018")

    body = [c for c in fake.calls if c[0] == "POST"][0][2]["body"].decode()
    assert "to_folder_copy=Copy+files" in body
    assert "to_folder_move" not in body


# ---------------------------------------------------------------------------
# flag toggles — one GET per file_id, with set_public / set_premium_only
# ---------------------------------------------------------------------------

def test_filespace_set_file_public_sends_one_get_per_file():
    """set_file_public issues a GET per numeric file_id with set_public=true."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files&fld_id=0": html,
        "https://filespace.com/?op=my_files&file_id=": b"1",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    result = client.set_file_public(
        ["3zm41fbivvgp", "i7off4ja4vio"], True
    )

    assert result.all_succeeded
    flag_calls = [
        c for c in fake.calls
        if c[0] == "GET" and "set_public=true" in c[1]
    ]
    assert len(flag_calls) == 2
    urls = {c[1] for c in flag_calls}
    assert any("file_id=7265936" in u for u in urls)
    assert any("file_id=7265934" in u for u in urls)


def test_filespace_set_file_public_false_sends_set_public_false():
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files&fld_id=0": html,
        "https://filespace.com/?op=my_files&file_id=": b"1",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    client.set_file_public(["3zm41fbivvgp"], False)

    flag_calls = [c for c in fake.calls if "set_public=false" in c[1]]
    assert len(flag_calls) == 1


def test_filespace_set_file_premium_sends_set_premium_only():
    """set_file_premium uses set_premium_only query param."""
    html = _load_my_files()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=my_files&fld_id=0": html,
        "https://filespace.com/?op=my_files&file_id=": b"1",
    })
    client = FilespaceFileManagerClient(fake)
    client.list_files("/")

    client.set_file_premium(["3zm41fbivvgp"], True)

    flag_calls = [
        c for c in fake.calls
        if c[0] == "GET" and "set_premium_only=true" in c[1]
    ]
    assert len(flag_calls) == 1
    assert "file_id=7265936" in flag_calls[0][1]


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------

def test_filespace_read_file_properties_parses_fixture():
    """read_file_properties pulls all XFS file-edit fields from HTML."""
    edit_html = _load_file_edit()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=file_edit": edit_html,
    })
    client = FilespaceFileManagerClient(fake)

    props = client.read_file_properties("3zm41fbivvgp")

    assert props["file_name"] == "Test114b.zip"
    assert props["file_descr"] == "a description"
    assert props["file_password"] == ""
    assert props["file_price"] == "0"
    assert props["file_public"] == "1"
    assert props["file_premium_only"] == "0"


def test_filespace_update_file_properties_single_roundtrip():
    """update_file_properties with round_trip=True reads then writes."""
    edit_html = _load_file_edit()
    fake = FakeFileHostClient({
        "https://filespace.com/?op=file_edit": edit_html,
    })
    client = FilespaceFileManagerClient(fake)

    result = client.update_file_properties(
        ["3zm41fbivvgp"], {"file_descr": "updated"}, round_trip=True,
    )

    assert result.succeeded == ["3zm41fbivvgp"]
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert len(posts) == 1
    body = posts[0][2]["body"].decode("utf-8")
    assert "file_name=Test114b.zip" in body
    assert "file_descr=updated" in body
    assert "op=file_edit" in body
    assert "token=" not in body


def test_filespace_update_file_properties_multi_is_diff_only():
    """Multi-file update posts only the diff keys, no round-trip read."""
    fake = FakeFileHostClient({
        "https://filespace.com/?op=file_edit": b"<html>ok</html>",
    })
    client = FilespaceFileManagerClient(fake)

    result = client.update_file_properties(
        ["code_a", "code_b"],
        {"file_password": "secret", "file_name": "ignored"},
        round_trip=False,
    )

    assert set(result.succeeded) == {"code_a", "code_b"}
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert len(posts) == 2
    for _m, _u, kwargs in posts:
        body = kwargs["body"].decode("utf-8")
        assert "file_password=secret" in body
        # file_name is stripped in multi-file mode
        assert "file_name=" not in body
