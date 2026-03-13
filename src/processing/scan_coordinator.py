"""Multi-host scan coordinator.

Orchestrates concurrent per-host checking for a set of galleries.
Groups galleries by host, creates the appropriate checker, runs all host
checks concurrently, collects results, and writes them to the database.

IMX galleries are NOT handled here — they are routed to the existing
RenameWorker/ImageStatusChecker pipeline and their results are written
to host_scan_results by the caller after completion.
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


# File hosts that use the K2S API (getFilesList)
K2S_FAMILY_HOSTS = frozenset({'keep2share', 'fileboom', 'tezfiles'})

# K2S API base URLs by host_id
K2S_API_BASES = {
    'keep2share': 'https://k2s.cc/api/v2',
    'fileboom': 'https://fboom.me/api/v2',
    'tezfiles': 'https://tezfiles.com/api/v2',
}


@dataclass
class HostScanJob:
    """Describes a scan job for one host across multiple galleries."""
    host_type: str  # 'image' or 'file'
    host_id: str
    galleries: List[Dict[str, Any]]
    # For image hosts: each gallery has 'db_id', 'path', 'thumb_urls'
    # For K2S-family: each gallery has 'db_id', 'file_ids' (dict of file_id -> url)
    # For RapidGator: each gallery has 'db_id', 'download_urls' (list)


class ScanCoordinator:
    """Orchestrates concurrent per-host link scanning.

    Usage:
        coord = ScanCoordinator(store=queue_store, connection_limiter=limiter)
        coord.start_scan(gallery_data, file_upload_data, credentials)
        # ... progress via callback ...
        # results written to host_scan_results table on completion
    """

    def __init__(
        self,
        store: Any,
        connection_limiter: ConnectionLimiter,
        credentials: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[str, str, int, int], None]] = None,
        completion_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._store = store
        self._connection_limiter = connection_limiter
        self._credentials = credentials or {}
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
            image_jobs = self._build_image_host_jobs(image_galleries)
            file_jobs = self._build_file_host_jobs(file_uploads)
            all_jobs = image_jobs + file_jobs

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
                })

        except Exception as e:
            log(f"Scan coordinator error: {e}", level="error", category="scanner")

    def _run_job(self, job: HostScanJob) -> List[Tuple]:
        if self._cancelled.is_set():
            return []

        if job.host_type == 'image':
            return self._run_image_host_job(job)
        elif job.host_id in K2S_FAMILY_HOSTS:
            return self._run_k2s_job(job)
        elif job.host_id == 'rapidgator':
            return self._run_rapidgator_job(job)
        else:
            log(f"No checker for host {job.host_id}, skipping", level="warning", category="scanner")
            return []

    def _run_image_host_job(self, job: HostScanJob) -> List[Tuple]:
        checker = ThumbnailChecker(max_workers=2)
        results = []
        now = int(time.time())

        for gallery in job.galleries:
            if self._cancelled.is_set():
                break

            thumb_urls = gallery.get('thumb_urls', [])
            db_id = gallery['db_id']

            def on_progress(checked, total):
                if self._progress_callback:
                    self._progress_callback(job.host_type, job.host_id, checked, total)

            check_result = checker.check_gallery(
                thumb_urls,
                cancel_event=self._cancelled,
                progress_callback=on_progress,
            )

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
            log(f"Missing API config or credentials for {job.host_id}", level="warning", category="scanner")
            return []

        checker = K2SFileChecker(api_base=api_base, auth_token=token)
        results = []
        now = int(time.time())

        for gallery in job.galleries:
            if self._cancelled.is_set():
                break

            file_ids = gallery.get('file_ids', {})
            db_id = gallery['db_id']

            check_result = checker.check_gallery(file_ids)

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

        for gallery in job.galleries:
            if self._cancelled.is_set():
                break

            download_urls = gallery.get('download_urls', [])
            db_id = gallery['db_id']

            check_result = checker.check_gallery(download_urls)

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

    def _build_image_host_jobs(
        self, galleries: List[Dict[str, Any]]
    ) -> List[HostScanJob]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for gal in galleries:
            host_id = gal.get('image_host_id', 'imx')
            if host_id == 'imx':
                continue  # IMX uses existing checker
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
