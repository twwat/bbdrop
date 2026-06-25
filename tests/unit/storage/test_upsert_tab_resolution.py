"""
Test suite for atomic tab_id resolution during gallery upsert.

Tests verify:
1. Tab_id is resolved from tab_name at INSERT time via subquery
2. If tab is deleted before INSERT completes, gallery defaults to Main tab
3. Race condition between SELECT tab_id and INSERT is eliminated
"""

import pytest
import sqlite3
import os
import tempfile
import time
from unittest.mock import patch

from src.storage.database import QueueStore, _connect, _ensure_schema


@pytest.fixture
def temp_db():
    """Create a temporary test database."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    yield path

    # Cleanup
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def queue_store(temp_db):
    """Create a QueueStore instance with temporary database."""
    store = QueueStore(db_path=temp_db)
    yield store
    # Cleanup
    if hasattr(store, '_executor'):
        store._executor.shutdown(wait=True)


class TestTabResolution:
    """Test atomic tab_id resolution at INSERT time."""

    def test_existing_tab_resolves_correctly(self, queue_store):
        """
        Test that a gallery upserted with an existing tab_name
        gets the correct tab_id.

        PASS criteria: Gallery tab_id matches the created tab's id.
        This also verifies on old code since the tab exists at both
        SELECT and INSERT time.
        """
        # Create a user tab
        tab_id = queue_store.create_tab('TestTab')
        assert tab_id > 0

        # Upsert a gallery with that tab_name
        item = {
            'path': '/test/gallery1',
            'name': 'Test Gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': 'TestTab'
        }
        queue_store.bulk_upsert([item])

        # Load and verify tab_id
        items = queue_store.load_all_items()
        assert len(items) == 1
        loaded_tab_id = items[0].get('tab_id')

        # The gallery's tab_id should match the created tab
        assert loaded_tab_id == tab_id, (
            f"Gallery tab_id {loaded_tab_id} should match created tab {tab_id}"
        )

    def test_nonexistent_tab_defaults_to_main(self, queue_store):
        """
        Test that a gallery upserted with a non-existent tab_name
        defaults to the Main tab.

        PASS criteria: Gallery tab_id == Main tab's id (should be 1).
        This verifies the COALESCE fallback works.
        """
        # Get Main tab id (should be 1 in a fresh DB)
        tabs = queue_store.get_all_tabs()
        main_tab = next(tab for tab in tabs if tab['name'] == 'Main')
        main_tab_id = main_tab['id']

        # Upsert a gallery with a non-existent tab_name
        item = {
            'path': '/test/gallery_orphan',
            'name': 'Orphan Gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': 'GhostTab'  # This tab doesn't exist
        }
        queue_store.bulk_upsert([item])

        # Load and verify tab_id
        items = queue_store.load_all_items()
        assert len(items) == 1
        loaded_tab_id = items[0].get('tab_id')

        # The gallery should default to Main tab
        assert loaded_tab_id == main_tab_id, (
            f"Gallery with non-existent tab should default to Main (id={main_tab_id}), "
            f"but got tab_id={loaded_tab_id}"
        )

    def test_race_deleted_tab_defaults_to_main(self, queue_store):
        """
        Test the race condition: tab exists at SELECT time but is deleted
        before INSERT executes. Gallery should land in Main tab, not orphaned.

        This test directly simulates the race by:
        1. Creating a tab 'RaceTab'
        2. Preparing an item with tab_name='RaceTab'
        3. Directly deleting 'RaceTab' before the upsert
        4. Upserting the item
        5. Verifying the gallery's tab_id == Main tab id

        FAIL on old code (tab_id resolving before DELETE happens):
          Old code: SELECT tab_id=X, then DELETE tab X, then INSERT tab_id=X → orphaned
        PASS on new code (tab_id resolved at INSERT time):
          New code: DELETE tab, then INSERT... tab_id subquery finds no row,
          COALESCE returns 1 (Main) → gallery in Main

        This deterministically proves the fix.
        """
        # Create a tab
        race_tab_id = queue_store.create_tab('RaceTab')
        assert race_tab_id > 0

        # Get Main tab id
        tabs = queue_store.get_all_tabs()
        main_tab = next(tab for tab in tabs if tab['name'] == 'Main')
        main_tab_id = main_tab['id']

        # Prepare an item that references the soon-to-be-deleted tab
        item = {
            'path': '/test/gallery_race',
            'name': 'Race Gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': 'RaceTab'
        }

        # Delete the tab BEFORE upsert
        # This simulates the race: tab is deleted after the in-memory item is created
        # but before the DB INSERT executes
        queue_store.delete_tab(race_tab_id)

        # Now upsert the item
        # Old code: Would store the stale race_tab_id → orphaned
        # New code: Resolves tab_id at INSERT time, finds no RaceTab,
        #          COALESCE returns 1 (Main) → not orphaned
        queue_store.bulk_upsert([item])

        # Load and verify
        items = queue_store.load_all_items()
        assert len(items) == 1
        loaded_tab_id = items[0].get('tab_id')

        # The gallery should NOT be orphaned; it should be in Main
        assert loaded_tab_id == main_tab_id, (
            f"Gallery upserted after its tab was deleted should land in Main (id={main_tab_id}), "
            f"but got tab_id={loaded_tab_id}. This indicates the race condition is NOT fixed."
        )

        # Also verify the gallery is actually visible (not filtered out)
        all_items_from_main = queue_store.load_items_by_tab('Main')
        paths_in_main = [item['path'] for item in all_items_from_main]
        assert '/test/gallery_race' in paths_in_main, (
            "Gallery should be visible in Main tab after race condition"
        )

    def test_tab_name_fallback_to_main(self, queue_store):
        """
        Test that if tab_name is None or empty, it falls back to 'Main'.

        This verifies the Python-level fallback logic still works.
        """
        # Get Main tab id
        tabs = queue_store.get_all_tabs()
        main_tab = next(tab for tab in tabs if tab['name'] == 'Main')
        main_tab_id = main_tab['id']

        # Upsert with None tab_name
        item = {
            'path': '/test/gallery_no_tab',
            'name': 'No Tab Gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': None
        }
        queue_store.bulk_upsert([item])

        items = queue_store.load_all_items()
        assert len(items) == 1
        loaded_tab_id = items[0].get('tab_id')

        assert loaded_tab_id == main_tab_id, (
            f"Gallery with None tab_name should default to Main (id={main_tab_id}), "
            f"but got tab_id={loaded_tab_id}"
        )

    def test_tab_id_preserved_on_update(self, queue_store):
        """
        Test that ON CONFLICT DO UPDATE preserves tab_id correctly.

        When updating a gallery, if tab_id resolves via subquery the first time,
        the UPDATE should use the correct tab_id from excluded.tab_id.
        """
        # Create a tab
        tab_id = queue_store.create_tab('PersistTab')

        # First upsert
        item = {
            'path': '/test/gallery_persist',
            'name': 'Persist Gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': 'PersistTab'
        }
        queue_store.bulk_upsert([item])

        # Verify initial insert
        items = queue_store.load_all_items()
        assert len(items) == 1
        assert items[0]['tab_id'] == tab_id

        # Update the gallery (same path)
        item['name'] = 'Updated Name'
        item['status'] = 'completed'
        queue_store.bulk_upsert([item])

        # Verify update and that tab_id was preserved
        items = queue_store.load_all_items()
        assert len(items) == 1
        assert items[0]['name'] == 'Updated Name'
        assert items[0]['status'] == 'completed'
        assert items[0]['tab_id'] == tab_id, (
            "tab_id should be preserved during ON CONFLICT UPDATE"
        )
