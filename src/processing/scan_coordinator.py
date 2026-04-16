"""Multi-host scan coordinator.

Orchestrates concurrent per-host checking for a set of galleries.
Groups galleries by host, creates the appropriate checker, runs all host
checks concurrently, collects results, and writes them to the database.

IMX galleries are checked via the RenameWorker's /user/moderate endpoint
(single POST, near-instantaneous). Other image hosts (Turbo, etc.) use
ThumbnailChecker (HEAD requests + ETag matching).
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple

from src.network.thumbnail_checker import ThumbnailChecker
from src.network.k2s_file_checker import K2SFileChecker
from src.network.rapidgator_file_checker import RapidgatorFileChecker
from src.network.connection_limiter import ConnectionLimiter
from src.utils.logger import log


# File hosts that use the K2S API (getFilesInfo)
K2S_FAMILY_HOSTS = frozenset({'keep2share', 'fileboom', 'tezfiles'})

# K2S API base URLs by host_id
K2S_API_BASES = {
    'keep2share': 'https://k2s.cc/api/v2',
    'fileboom': 'https://fboom.me/api/v2',
    'tezfiles': 'https://tezfiles.com/api/v2',
}

# File hosts with no checker implementation yet
UNSUPPORTED_FILE_HOSTS = frozenset({'filedot', 'filespace'})


@dataclass
class HostScanJob:
    """Describes a scan job for one host across multiple galleries."""
    host_type: str  # 'image' or 'file'
    host_id: str
    galleries: List[Dict[str, Any]]
    # For image hosts: each gallery has 'db_id', 'path', 'thumb_urls'
    # For K2S-family: each gallery has 'db_id', 'file_ids' (dict of file_id -> url)
    # For RapidGator: each gallery has 'db_id', 'download_urls' (list)


def _load_file_host_credentials() -> Dict[str, str]:
    """Load decrypted credentials/tokens for file hosts from OS keyring.

    For K2S-family hosts (api_key auth), the decrypted credential IS the
    access token. For RapidGator (token_login), tries the token cache first,
    then falls back to login.

    Returns:
        Dict mapping host_id to auth token string.
    """
    credentials: Dict[str, str] = {}

    try:
        from src.utils.credentials import get_credential, decrypt_password
    except ImportError:
        log("Credentials module not available", level="error", category="scanner")
        return credentials

    # K2S-family: api_key auth — decrypted credential IS the token
    for host_id in K2S_FAMILY_HOSTS:
        encrypted = get_credential(f'file_host_{host_id}_credentials')
        if encrypted:
            try:
                decrypted = decrypt_password(encrypted)
                if decrypted:
                    credentials[host_id] = decrypted
            except Exception as e:
                log(f"Failed to decrypt {host_id} credentials: {e}",
                    level="warning", category="scanner")

    # RapidGator: token_login auth — try cached token first
    try:
        from src.network.token_cache import get_token_cache
        token_cache = get_token_cache()
        cached_token = token_cache.get_token('rapidgator')
        if cached_token:
            credentials['rapidgator'] = cached_token
        else:
            # Try to login with stored credentials
            encrypted = get_credential('file_host_rapidgator_credentials')
            if encrypted:
                decrypted = decrypt_password(encrypted)
                if decrypted:
                    from src.core.file_host_config import get_config_manager
                    config_mgr = get_config_manager()
                    rg_config = config_mgr.get_host_config('rapidgator')
                    if rg_config:
                        from src.network.file_host_client import FileHostClient
                        client = FileHostClient(rg_config, credentials=decrypted, host_id='rapidgator')
                        if client.auth_token:
                            credentials['rapidgator'] = client.auth_token
    except Exception as e:
        log(f"Failed to get rapidgator token: {e}", level="warning", category="scanner")

    return credentials


class ScanCoordinator:
    """Orchestrates concurrent per-host link scanning.

    Usage:
        coord = ScanCoordinator(store=queue_store, connection_limiter=limiter)
        coord.start_scan(gallery_data, file_upload_data)
        # ... progress via callback ...
        # results written to host_scan_results table on completion
    """

    def __init__(
        self,
        store: Any,
        connection_limiter: ConnectionLimiter,
        credentials: Optional[Dict[str, str]] = None,
        rename_worker: Any = None,
        progress_callback: Optional[Callable[[str, str, int, int, int, int], None]] = None,
        completion_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._store = store
        self._connection_limiter = connection_limiter
        self._credentials = credentials or {}
        self._rename_worker = rename_worker
        self._progress_callback = progress_callback
        self._completion_callback = completion_callback
        self._cancelled = threading.Event()
        self._scan_thread: Optional[threading.Thread] = None

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()
        log("Scan cancelled by user", level="info", category="scanner")

    def start_scan(
        self,
        image_galleries: List[Dict[str, Any]],
        file_uploads: List[Dict[str, Any]],
    ) -> None:
        # Load credentials if none were provided
        if not self._credentials:
            self._credentials = _load_file_host_credentials()

        self._cancelled.clear()
        self._scan_thread = threading.Thread(
            target=self._run_scan,
            args=(image_galleries, file_uploads),
            daemon=True,
            name="ScanCoordinator",
        )
        self._scan_thread.start()

    def _run_scan(
        self,
        image_galleries: List[Dict[str, Any]],
        file_uploads: List[Dict[str, Any]],
    ) -> None:
        start_time = time.time()
        all_results: List[Tuple[int, str, str, str, int, int, int, Optional[str]]] = []

        try:
            imx_job = self._build_imx_job(image_galleries)
            image_jobs = self._build_image_host_jobs(image_galleries)
            file_jobs = self._build_file_host_jobs(file_uploads)
            all_jobs = ([imx_job] if imx_job else []) + image_jobs + file_jobs

            if not all_jobs:
                log("No scan jobs to run", level="info", category="scanner")
                if self._completion_callback:
                    self._completion_callback({'total_hosts': 0, 'total_galleries': 0, 'elapsed': 0})
                return

            log(f"Starting scan: {len(all_jobs)} host jobs ({len(image_jobs)} image, {len(file_jobs)} file)",
                level="info", category="scanner")

            with ThreadPoolExecutor(max_workers=len(all_jobs), thread_name_prefix="scan") as executor:
                future_to_job = {}
                for job in all_jobs:
                    future = executor.submit(self._run_job, job)
                    future_to_job[future] = job

                for future in as_completed(future_to_job):
                    if self._cancelled.is_set():
                        break
                    job = future_to_job[future]
                    try:
                        results = future.result()
                        all_results.extend(results)
                    except Exception as e:
                        log(f"Scan job failed for {job.host_id}: {e}", level="error", category="scanner")

            if all_results and not self._cancelled.is_set():
                self._store.bulk_upsert_scan_results(all_results)
                log(f"Wrote {len(all_results)} scan results to database",
                    level="info", category="scanner")

            elapsed = time.time() - start_time
            if self._completion_callback:
                self._completion_callback({
                    'total_hosts': len(all_jobs),
                    'total_galleries': len(all_results),
                    'elapsed': elapsed,
                    'k2s_storage_used': getattr(self, '_k2s_storage_used', None),
                })

        except Exception as e:
            log(f"Scan coordinator error: {e}", level="error", category="scanner")

    def _run_job(self, job: HostScanJob) -> List[Tuple]:
        if self._cancelled.is_set():
            return []

        if job.host_id == 'imx':
            return self._run_imx_job(job)
        elif job.host_type == 'image':
            return self._run_image_host_job(job)
        elif job.host_id in K2S_FAMILY_HOSTS:
            return self._run_k2s_job(job)
        elif job.host_id == 'rapidgator':
            return self._run_rapidgator_job(job)
        elif job.host_id in UNSUPPORTED_FILE_HOSTS:
            log(f"No checker implemented for {job.host_id} yet", level="info", category="scanner")
            return []
        else:
            log(f"No checker for host {job.host_id}, skipping", level="warning", category="scanner")
            return []

    def _run_image_host_job(self, job: HostScanJob) -> List[Tuple]:
        checker = ThumbnailChecker(max_workers=2)
        results = []
        now = int(time.time())

        # Calculate cumulative total for meaningful progress reporting
        total_for_host = sum(len(g.get('thumb_urls', [])) for g in job.galleries)
        cumulative_checked = 0
        cumulative_online = 0
        cumulative_items = 0

        for gallery in job.galleries:
            if self._cancelled.is_set():
                break

            thumb_urls = gallery.get('thumb_urls', [])
            db_id = gallery['db_id']
            gallery_base = cumulative_checked

            _cum_online = cumulative_online
            _cum_items = cumulative_items
            def on_progress(checked, total, _base=gallery_base, _host_total=total_for_host,
                            _online=_cum_online, _items=_cum_items):
                if self._progress_callback:
                    self._progress_callback(job.host_type, job.host_id, _base + checked, _host_total,
                                            _online, _items)

            check_result = checker.check_gallery(
                thumb_urls,
                cancel_event=self._cancelled,
                progress_callback=on_progress,
            )

            cumulative_checked += len(thumb_urls)
            cumulative_online += check_result.get('online', 0)
            cumulative_items += check_result.get('online', 0) + check_result.get('offline', 0) + check_result.get('errors', 0)

            detail = None
            if check_result.get('offline_urls'):
                detail = json.dumps({'offline_urls': check_result['offline_urls']})

            results.append((
                db_id,
                job.host_type,
                job.host_id,
                check_result['status'],
                check_result['online'],
                check_result.get('online', 0) + check_result.get('offline', 0) + check_result.get('errors', 0),
                now,
                detail,
            ))

        return results

    def _run_k2s_job(self, job: HostScanJob) -> List[Tuple]:
        api_base = K2S_API_BASES.get(job.host_id, '')
        token = self._credentials.get(job.host_id, '')
        if not api_base or not token:
            log(f"Missing API config or credentials for {job.host_id}",
                level="warning", category="scanner")
            return []

        checker = K2SFileChecker(api_base=api_base, auth_token=token)

        # Use cached inventory if another K2S family host already walked this account
        if not hasattr(self, '_k2s_inventory'):
            self._k2s_inventory = {}
        if not hasattr(self, '_k2s_storage_used'):
            self._k2s_storage_used = None

        if not self._k2s_inventory:
            log(f"Walking K2S account folders via {job.host_id}",
                level="info", category="scanner")
            all_files = checker.get_all_files()
            self._k2s_inventory = {f['id']: f for f in all_files}
            self._k2s_storage_used = checker.calc_storage_used(all_files)
            log(f"K2S folder walk complete: {len(all_files)} files, "
                f"{self._k2s_storage_used} bytes used",
                level="info", category="scanner")

        results = []
        now = int(time.time())
        gallery_count = len(job.galleries)
        cumulative_online = 0
        cumulative_items = 0

        for i, gallery in enumerate(job.galleries):
            if self._cancelled.is_set():
                break

            file_ids = gallery.get('file_ids', {})
            db_id = gallery['db_id']

            check_result = checker.check_gallery_from_inventory(
                file_ids, self._k2s_inventory)

            cumulative_online += check_result.get('online', 0)
            cumulative_items += check_result.get('total', 0)
            if self._progress_callback:
                self._progress_callback(job.host_type, job.host_id, i + 1,
                                        gallery_count, cumulative_online,
                                        cumulative_items)

            detail = None
            if check_result.get('offline_urls'):
                detail = json.dumps({'offline_urls': check_result['offline_urls']})

            results.append((
                db_id,
                job.host_type,
                job.host_id,
                check_result['status'],
                check_result['online'],
                check_result['total'],
                now,
                detail,
            ))

        return results

    def _run_rapidgator_job(self, job: HostScanJob) -> List[Tuple]:
        token = self._credentials.get('rapidgator', '')
        if not token:
            log("Missing credentials for rapidgator", level="warning", category="scanner")
            return []

        checker = RapidgatorFileChecker(auth_token=token)
        results = []
        now = int(time.time())
        gallery_count = len(job.galleries)
        cumulative_online = 0
        cumulative_items = 0

        for i, gallery in enumerate(job.galleries):
            if self._cancelled.is_set():
                break

            download_urls = gallery.get('download_urls', [])
            db_id = gallery['db_id']

            check_result = checker.check_gallery(download_urls)

            # Report per-gallery progress
            cumulative_online += check_result.get('online', 0)
            cumulative_items += check_result.get('total', 0)
            if self._progress_callback:
                self._progress_callback(job.host_type, job.host_id, i + 1, gallery_count,
                                        cumulative_online, cumulative_items)

            detail = None
            if check_result.get('offline_urls'):
                detail = json.dumps({'offline_urls': check_result['offline_urls']})

            results.append((
                db_id,
                job.host_type,
                job.host_id,
                check_result['status'],
                check_result['online'],
                check_result['total'],
                now,
                detail,
            ))

        return results

    def _build_imx_job(self, galleries: List[Dict[str, Any]]) -> Optional[HostScanJob]:
        """Build a single IMX job if there are IMX galleries to scan."""
        imx_galleries = [g for g in galleries if g.get('image_host_id', 'imx') == 'imx']
        if not imx_galleries:
            return None
        return HostScanJob(host_type='image', host_id='imx', galleries=imx_galleries)

    def _run_imx_job(self, job: HostScanJob) -> List[Tuple]:
        """Check IMX galleries via the RenameWorker's /user/moderate endpoint.

        This is a single POST with all image URLs — near-instantaneous compared
        to per-thumbnail HEAD requests.
        """
        if not self._rename_worker:
            log("No RenameWorker available for IMX scan — skipping", level="warning", category="scanner")
            return []

        rw = self._rename_worker
        if not getattr(rw, 'login_successful', False):
            log("RenameWorker not authenticated — skipping IMX scan", level="warning", category="scanner")
            return []

        # Build galleries_data in the format _perform_status_check expects
        galleries_data = []
        for gal in job.galleries:
            image_urls = gal.get('image_urls', [])
            if not image_urls:
                continue
            galleries_data.append({
                'db_id': gal['db_id'],
                'path': f"__scan__{gal['db_id']}",  # synthetic path as key
                'name': gal.get('name', ''),
                'image_urls': image_urls,
            })

        if not galleries_data:
            return []

        total_galleries = len(galleries_data)
        if self._progress_callback:
            self._progress_callback('image', 'imx', 0, total_galleries, 0, 0)

        try:
            raw_results = rw._perform_status_check(galleries_data)
        except Exception as e:
            log(f"IMX moderate check failed: {e}", level="error", category="scanner")
            return []

        imx_online = sum(1 for r in raw_results.values() if r.get('online', 0) > 0
                         and r.get('offline', 0) == 0)
        imx_total_items = sum(r.get('total', 0) for r in raw_results.values())
        imx_online_items = sum(r.get('online', 0) for r in raw_results.values())
        if self._progress_callback:
            self._progress_callback('image', 'imx', total_galleries, total_galleries,
                                    imx_online_items, imx_total_items)

        # Convert RenameWorker result format to scan_coordinator tuple format
        results = []
        now = int(time.time())
        for gal in galleries_data:
            path = gal['path']
            db_id = gal['db_id']
            r = raw_results.get(path, {})
            online = r.get('online', 0)
            total = r.get('total', 0)
            offline = r.get('offline', 0)

            if total == 0:
                status = 'unknown'
            elif offline == 0:
                status = 'online'
            elif online == 0:
                status = 'offline'
            else:
                status = 'partial'

            detail = None
            if r.get('offline_urls'):
                detail = json.dumps({'offline_urls': r['offline_urls']})

            results.append((db_id, 'image', 'imx', status, online, total, now, detail))

        return results

    def _build_image_host_jobs(
        self, galleries: List[Dict[str, Any]]
    ) -> List[HostScanJob]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for gal in galleries:
            host_id = gal.get('image_host_id', 'imx')
            if host_id == 'imx':
                continue  # IMX handled separately via _run_imx_job
            if host_id not in groups:
                groups[host_id] = []
            groups[host_id].append(gal)

        return [
            HostScanJob(host_type='image', host_id=hid, galleries=gals)
            for hid, gals in groups.items()
        ]

    def _build_file_host_jobs(
        self, file_uploads: List[Dict[str, Any]]
    ) -> List[HostScanJob]:
        host_gallery_map: Dict[str, Dict[int, Dict[str, Any]]] = {}

        for upload in file_uploads:
            host_name = upload.get('host_name', '')
            gallery_fk = upload.get('gallery_fk')
            file_id = upload.get('file_id', '')
            download_url = upload.get('download_url', '')

            if not host_name or not gallery_fk:
                continue

            if host_name not in host_gallery_map:
                host_gallery_map[host_name] = {}
            if gallery_fk not in host_gallery_map[host_name]:
                host_gallery_map[host_name][gallery_fk] = {
                    'db_id': gallery_fk,
                    'file_ids': {},
                    'download_urls': [],
                }

            gal_data = host_gallery_map[host_name][gallery_fk]
            if file_id:
                gal_data['file_ids'][file_id] = download_url
            if download_url:
                gal_data['download_urls'].append(download_url)

        jobs = []
        for host_name, gal_map in host_gallery_map.items():
            jobs.append(HostScanJob(
                host_type='file',
                host_id=host_name,
                galleries=list(gal_map.values()),
            ))

        return jobs
