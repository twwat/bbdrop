"""When has every file host finished with a gallery?

Used by the gallery-completed notification. Decides per host, from the
host's head row (part 0), because a multi-part failure only writes the
head row as failed and leaves the failing part's row at 'uploading'.

A failed K2S-family head row is not final while a sibling has completed:
HostFamilyCoordinator turns it into a dedup_only hash-copy retry. Only a
failed retry (dedup_only=1) is final.
"""

from typing import List, Optional

from src.core.file_host_config import get_host_family, is_family_dedup_enabled


def _row_done(row: dict) -> bool:
    return bool(row.get('deduped')) or row.get('status') in ('completed', 'cancelled')


def settled_failed_hosts(rows: List[dict], failed_host: str = '') -> Optional[List[str]]:
    """Return the failed host ids once every host has settled, else None.

    ``failed_host`` is a host whose terminal failure has been signalled but
    may not be written yet (the worker emits upload_failed before the write).
    Cancelled hosts count as settled and are not reported as failed.
    """
    by_host: dict = {}
    for row in rows:
        by_host.setdefault(row.get('host_name', ''), []).append(row)

    won = {
        host for host, host_rows in by_host.items()
        if min(host_rows, key=lambda r: r.get('part_number', 0)).get('status') == 'completed'
    }

    failed = []
    for host, host_rows in by_host.items():
        if all(_row_done(r) for r in host_rows):
            continue
        head = min(host_rows, key=lambda r: r.get('part_number', 0))
        if not (head.get('status') == 'failed' or (failed_host and host == failed_host)):
            return None
        if not head.get('dedup_only') and _hash_retry_expected(host, won):
            return None
        failed.append(host)
    return failed


def _hash_retry_expected(host: str, won: set) -> bool:
    """True if the family coordinator will retry ``host`` from a sibling's copy."""
    family = get_host_family(host)
    if not family:
        return False
    if not any(h != host and get_host_family(h) == family for h in won):
        return False
    return is_family_dedup_enabled()
