"""BBCode regeneration must not wipe the stats recorded at upload time."""
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.processing.artifact_handler import ArtifactHandler

pytestmark = pytest.mark.unit

GALLERY_ID = "1nz9k"
NAME = "Test Gallery"


def _write_json(gallery_dir, stats, settings, started_at="2026-10-24 08:48:05"):
    uploaded = os.path.join(gallery_dir, ".uploaded")
    os.makedirs(uploaded, exist_ok=True)
    path = os.path.join(uploaded, f"{NAME}_{GALLERY_ID}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {"gallery_name": NAME, "gallery_id": GALLERY_ID,
                     "gallery_url": "https://imx.to/g/1nz9k",
                     "started_at": started_at, "media_type": "image"},
            "settings": settings,
            "stats": stats,
            "images": [],
            "failures": [],
        }, f)
    return path


def _item(gallery_dir, **dims):
    return SimpleNamespace(
        path=gallery_dir, name=NAME, gallery_id=GALLERY_ID,
        gallery_url="https://imx.to/g/1nz9k", cover_result=None, db_id=None,
        custom1="", custom2="", custom3="", custom4="",
        ext1="", ext2="", ext3="", ext4="", **dims,
    )


def _regenerate(gallery_dir, item):
    qm = SimpleNamespace(get_item=lambda p: item)
    handler = ArtifactHandler(qm, {})
    with patch("src.utils.templates.save_gallery_artifacts") as save:
        handler.regenerate_gallery_bbcode(gallery_dir, "default")
    return save.call_args.kwargs["results"]


FULL_STATS = {
    "total_images": 67, "successful_count": 67, "failed_count": 0,
    "upload_time": 11.197, "total_size": 129632047, "uploaded_size": 129632047,
    "avg_width": 3600.0, "avg_height": 2400.0, "max_width": 3600.0,
    "max_height": 2700.0, "min_width": 2400.0, "min_height": 1600.0,
    "transfer_speed_mb_s": 11.04,
}
SETTINGS = {"thumbnail_size": 3, "thumbnail_format": 2, "template_name": "Nubiles",
            "parallel_batch_size": 4, "video_details_template": ""}


def test_regeneration_keeps_upload_stats(tmp_path):
    gallery = str(tmp_path)
    _write_json(gallery, FULL_STATS, SETTINGS)

    results = _regenerate(gallery, _item(gallery))

    assert results["upload_time"] == 11.197
    assert results["uploaded_size"] == 129632047
    assert results["transfer_speed"] == pytest.approx(11.04 * 1024 * 1024)
    assert results["total_images"] == 67
    assert results["started_at"] == "2026-10-24 08:48:05"
    assert results["thumbnail_size"] == 3
    assert results["thumbnail_format"] == 2
    assert results["parallel_batch_size"] == 4
    assert results["max_height"] == 2700.0


def test_regeneration_fills_zero_dimensions_from_gallery_record(tmp_path):
    gallery = str(tmp_path)
    zero_dims = {**FULL_STATS, "avg_width": 0.0, "avg_height": 0.0, "max_width": 0.0,
                 "max_height": 0.0, "min_width": 0.0, "min_height": 0.0}
    _write_json(gallery, zero_dims, SETTINGS)
    item = _item(gallery, avg_width=3600.0, avg_height=2400.0, max_width=3600.0,
                 max_height=2700.0, min_width=2400.0, min_height=1600.0)

    results = _regenerate(gallery, item)

    assert (results["avg_width"], results["avg_height"]) == (3600.0, 2400.0)
    assert (results["max_width"], results["max_height"]) == (3600.0, 2700.0)
    assert (results["min_width"], results["min_height"]) == (2400.0, 1600.0)
