"""Tests for ArchiveManager temp-archive cleanup.

`release_archive` documented "Deletes when ref_count reaches 0" but the
non-force branch only reset the count to 0 and returned -- it never called
unlink. `cleanup_gallery` / `cleanup_all` were the only paths that deleted,
and neither was called anywhere in src/, so every upload archive leaked into
%TEMP% for the life of the machine.

These tests pin: refcount-0 deletes, shared refs survive until the last
release, and orphans from previous sessions can be swept at startup.
"""

import tempfile
from pathlib import Path

import pytest

from src.utils.archive_manager import ArchiveManager


def _seed(manager, db_id, paths, ref_count):
    """Put a fake cache entry in place without running a real zip."""
    manager.archive_cache[db_id] = (paths, ref_count)


def _make_zip(tmpdir, name):
    p = Path(tmpdir) / name
    p.write_bytes(b'\x00' * 32)
    return p


class TestCleanupGalleryDeletes:
    """cleanup_gallery is the terminal delete; release_archive is not.

    Retaining the archive at ref 0 is deliberate (see
    test_zip_manager.TestReleaseArchive.test_release_last_ref_keeps_for_retry)
    so an auto-retry can reuse it. The leak was that nothing ever called
    cleanup_gallery once the retry window closed.
    """

    @pytest.mark.unit
    def test_release_still_keeps_archive_for_retry(self):
        """The documented retry-reuse behaviour must be preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            zip_path = _make_zip(tmpdir, "bbdrop_1_Gallery.zip")
            _seed(manager, 1, [zip_path], 1)

            assert manager.release_archive(1) is False
            assert zip_path.exists()
            assert manager.archive_cache[1][1] == 0

    @pytest.mark.unit
    def test_cleanup_gallery_deletes_after_release(self):
        """Terminal cleanup removes the archive parked at ref 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            zip_path = _make_zip(tmpdir, "bbdrop_1_Gallery.zip")
            _seed(manager, 1, [zip_path], 1)
            manager.release_archive(1)

            manager.cleanup_gallery(1)

            assert not zip_path.exists()
            assert 1 not in manager.archive_cache

    @pytest.mark.unit
    def test_shared_reference_decrements(self):
        """Two hosts sharing an archive: first release only decrements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            zip_path = _make_zip(tmpdir, "bbdrop_2_Gallery.zip")
            _seed(manager, 2, [zip_path], 2)

            assert manager.release_archive(2) is False
            assert manager.archive_cache[2][1] == 1
            assert zip_path.exists(), "archive removed while a host still needs it"

    @pytest.mark.unit
    def test_all_parts_of_split_archive_deleted(self):
        """Every part of a split archive is removed, not just the first."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            parts = [
                _make_zip(tmpdir, "bbdrop_3_G.part1.rar"),
                _make_zip(tmpdir, "bbdrop_3_G.part2.rar"),
                _make_zip(tmpdir, "bbdrop_3_G.part3.rar"),
            ]
            _seed(manager, 3, parts, 1)

            manager.cleanup_gallery(3)
            assert not any(p.exists() for p in parts)

    @pytest.mark.unit
    def test_release_unknown_id_is_safe(self):
        manager = ArchiveManager()
        assert manager.release_archive(99999) is False

    @pytest.mark.unit
    def test_cleanup_of_already_missing_file_clears_cache(self):
        """A file deleted out from under us doesn't wedge the cache entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            zip_path = Path(tmpdir) / "gone.zip"
            _seed(manager, 4, [zip_path], 1)

            manager.cleanup_gallery(4)
            assert 4 not in manager.archive_cache


class TestSweepOrphans:
    @pytest.mark.unit
    def test_sweep_removes_orphaned_bbdrop_archives(self):
        """Stale bbdrop_* archives from previous sessions are reclaimed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            orphans = [
                _make_zip(tmpdir, "bbdrop_100_Old.zip"),
                _make_zip(tmpdir, "bbdrop_101_Old.part1.rar"),
                _make_zip(tmpdir, "bbdrop_102_Old.7z"),
            ]

            count, freed = manager.sweep_orphans()

            assert count == 3
            assert freed == 96  # 3 x 32 bytes
            assert not any(p.exists() for p in orphans)

    @pytest.mark.unit
    def test_sweep_covers_unnamed_gallery_fallback_name(self):
        """_generate_archive_name falls back to bbdrop_gallery_<id> when a
        gallery has no name (or one that sanitises to empty). Those orphans
        must be swept too."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            orphans = [
                _make_zip(tmpdir, "bbdrop_gallery_1.zip"),
                _make_zip(tmpdir, "bbdrop_gallery_42.part1.rar"),
                _make_zip(tmpdir, "bbdrop_7_Named.zip"),
            ]

            count, _ = manager.sweep_orphans()

            assert count == 3
            assert not any(p.exists() for p in orphans)

    @pytest.mark.unit
    def test_sweep_matches_real_generated_names(self):
        """Sweep the exact names _generate_archive_name produces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            named = manager._generate_archive_name(2278, "Nubiles 2026-08-15 Roxie")
            unnamed = manager._generate_archive_name(99, None)
            made = [_make_zip(tmpdir, f"{named}.zip"), _make_zip(tmpdir, f"{unnamed}.zip")]

            count, _ = manager.sweep_orphans()

            assert count == 2, f"sweep missed {[p.name for p in made if p.exists()]}"

    @pytest.mark.unit
    def test_sweep_ignores_unrelated_files(self):
        """Only bbdrop-prefixed archives are touched."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            keep = [
                _make_zip(tmpdir, "someone_elses.zip"),
                _make_zip(tmpdir, "bbdrop_notanumber.zip"),
                _make_zip(tmpdir, "important.txt"),
            ]

            count, _ = manager.sweep_orphans()

            assert count == 0
            assert all(p.exists() for p in keep)

    @pytest.mark.unit
    def test_sweep_skips_archives_in_use(self):
        """An archive tracked in the live cache is never swept."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir))
            active = _make_zip(tmpdir, "bbdrop_200_Active.zip")
            orphan = _make_zip(tmpdir, "bbdrop_201_Orphan.zip")
            _seed(manager, 200, [active], 1)

            count, _ = manager.sweep_orphans()

            assert count == 1
            assert active.exists(), "swept an archive that is currently uploading"
            assert not orphan.exists()

    @pytest.mark.unit
    def test_sweep_on_unreadable_temp_dir_is_safe(self):
        """A temp dir that can't be listed yields (0, 0) rather than raising.

        Scoped to a tmpdir on purpose -- ArchiveManager.__init__ mkdirs its
        temp_dir, so pointing a test at the real system temp would both
        create junk there and let the sweep loose on the developer's actual
        files.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager(temp_dir=Path(tmpdir) / "nested")
            assert manager.sweep_orphans() == (0, 0)
