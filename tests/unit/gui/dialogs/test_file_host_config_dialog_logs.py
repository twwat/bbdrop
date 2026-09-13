"""FileHostConfigDialog's log panel shows only this host's file_hosts lines."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.gui.dialogs.file_host_config_dialog import FileHostConfigDialog


@pytest.mark.unit
def test_initial_logs_match_host_prefix_in_file_hosts_category():
    log_text = "\n".join([
        "2026-09-12 10:00:00 INFO: [general] GUI loaded",
        "2026-09-12 10:00:01 INFO: [file_hosts] Filedot: Queued 'a.zip' (upload_id=1)",
        "2026-09-12 10:00:02 INFO: [file_hosts] RapidGator: Uploading 'b.zip'",
        "2026-09-12 10:00:03 INFO: [uploads] Starting upload: Filedot: odd name",
        "2026-09-12 10:00:04 DEBUG: [file_hosts] Filedot: Uploading 'a.zip'",
    ])
    stub = SimpleNamespace(host_config=SimpleNamespace(name="Filedot"), log_list=Mock())
    logger = Mock()
    logger.read_current_log.return_value = log_text

    with patch('src.utils.logging.get_logger', return_value=logger):
        FileHostConfigDialog._load_initial_logs(stub)

    # insertItem(0, …) is called oldest-first; each new one lands on top.
    shown = [c.args[1] for c in stub.log_list.insertItem.call_args_list]
    assert shown == [
        "2026-09-12 10:00:01 INFO: Filedot: Queued 'a.zip' (upload_id=1)",
        "2026-09-12 10:00:04 Filedot: Uploading 'a.zip'",
    ]
