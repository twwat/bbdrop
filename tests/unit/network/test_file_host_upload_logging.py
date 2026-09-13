"""Log line emitted by FileHostClient.upload_file before transfer."""

from unittest.mock import Mock

import pytest

from src.network.file_host_client import FileHostClient
from src.utils.format_utils import format_binary_size


def _bare_client(messages):
    """FileHostClient without __init__ — upload_file's logging path only needs
    _log_callback, config.upload_init_url and _with_token_retry."""
    client = FileHostClient.__new__(FileHostClient)
    client._log_callback = lambda msg, level: messages.append((msg, level))
    client.config = Mock(upload_init_url=None)
    client._with_token_retry = Mock(return_value={'status': 'success'})
    return client


@pytest.mark.unit
def test_uploading_line_strips_prefix_and_quotes_name(tmp_path):
    archive = tmp_path / "bbdrop_2328_Nubiles 2026-09-05 Nika One.zip"
    archive.write_bytes(b"x" * 5000)
    messages = []

    _bare_client(messages).upload_file(archive)

    assert messages[0] == (
        f"Uploading 'Nubiles 2026-09-05 Nika One.zip' ({format_binary_size(5000)})",
        "info",
    )


@pytest.mark.unit
def test_uploading_line_keeps_md5_suffix(tmp_path):
    archive = tmp_path / "bbdrop_1_Set.zip"
    archive.write_bytes(b"x" * 10)
    messages = []

    _bare_client(messages).upload_file(archive, md5_hash="abc123")

    assert messages[0][0] == f"Uploading 'Set.zip' ({format_binary_size(10)}) — MD5: abc123"
