"""settled_failed_hosts: when has every file host for a gallery finished?"""

from unittest.mock import patch

import pytest

from src.core.file_host_settlement import settled_failed_hosts


def _row(host, status, part=0, deduped=0, dedup_only=0):
    return {'host_name': host, 'status': status, 'part_number': part,
            'deduped': deduped, 'dedup_only': dedup_only}


@pytest.fixture(autouse=True)
def family_dedup_on():
    with patch('src.core.file_host_settlement.is_family_dedup_enabled',
               return_value=True) as enabled:
        yield enabled


def test_no_rows_is_settled():
    assert settled_failed_hosts([]) == []


def test_all_completed_or_deduped():
    rows = [_row('rapidgator', 'completed'), _row('tezfiles', 'pending', deduped=1)]
    assert settled_failed_hosts(rows) == []


@pytest.mark.parametrize("status", ['pending', 'uploading', 'blocked'])
def test_unfinished_row_waits(status):
    rows = [_row('rapidgator', 'completed'), _row('katfile', status)]
    assert settled_failed_hosts(rows) is None


def test_failed_non_family_host_is_final():
    rows = [_row('rapidgator', 'completed'), _row('katfile', 'failed')]
    assert settled_failed_hosts(rows) == ['katfile']


def test_cancelled_host_is_settled_but_not_failed():
    rows = [_row('rapidgator', 'completed'), _row('katfile', 'cancelled')]
    assert settled_failed_hosts(rows) == []


def test_failed_host_param_settles_row_still_uploading():
    rows = [_row('rapidgator', 'completed'), _row('katfile', 'uploading')]
    assert settled_failed_hosts(rows, failed_host='katfile') == ['katfile']


def test_failed_head_settles_orphan_later_part():
    # A part-2 failure marks only the head row failed; part 2 stays 'uploading'.
    rows = [_row('rapidgator', 'completed'),
            _row('katfile', 'failed', part=0), _row('katfile', 'uploading', part=1)]
    assert settled_failed_hosts(rows) == ['katfile']


def test_failed_family_host_waits_for_hash_retry_when_sibling_won():
    rows = [_row('keep2share', 'completed'), _row('tezfiles', 'failed')]
    assert settled_failed_hosts(rows) is None
    assert settled_failed_hosts(
        [_row('keep2share', 'completed'), _row('tezfiles', 'uploading')],
        failed_host='tezfiles') is None


def test_failed_hash_retry_is_final():
    rows = [_row('tezfiles', 'completed'), _row('keep2share', 'failed', dedup_only=1)]
    assert settled_failed_hosts(rows) == ['keep2share']


def test_failed_family_host_without_winner_is_final():
    rows = [_row('rapidgator', 'completed'), _row('tezfiles', 'failed')]
    assert settled_failed_hosts(rows) == ['tezfiles']


def test_family_dedup_off_means_failure_is_final(family_dedup_on):
    family_dedup_on.return_value = False
    rows = [_row('keep2share', 'completed'), _row('tezfiles', 'failed')]
    assert settled_failed_hosts(rows) == ['tezfiles']


def test_failed_hosts_in_first_seen_order():
    rows = [_row('katfile', 'failed'), _row('rapidgator', 'completed'),
            _row('ddownload', 'failed')]
    assert settled_failed_hosts(rows) == ['katfile', 'ddownload']
