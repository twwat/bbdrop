#!/usr/bin/env python3
"""Integration test for credential persistence - tests REAL storage, no mocks."""

import pytest
from bbdrop import get_credential, set_credential, encrypt_password, decrypt_password, remove_credential


def _has_real_keyring():
    """Check if a real keyring backend is available (not the fail backend)."""
    try:
        import keyring
        backend = keyring.get_keyring()
        return 'fail' not in type(backend).__module__
    except Exception:
        return False


@pytest.mark.skipif(not _has_real_keyring(), reason="No real keyring backend available")
class TestCredentialPersistence:
    """Test actual credential storage without mocking."""

    TEST_KEY = "file_host_INTEGRATION_TEST_credentials"

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test credentials before and after each test."""
        remove_credential(self.TEST_KEY)
        yield
        remove_credential(self.TEST_KEY)

    def test_credential_saves_and_loads(self):
        """Test that a saved credential can be loaded back."""
        # Save
        encrypted = encrypt_password("test_password")
        set_credential(self.TEST_KEY, encrypted)

        # Load
        loaded = get_credential(self.TEST_KEY)
        assert loaded is not None, "get_credential returned None"

        decrypted = decrypt_password(loaded)
        assert decrypted == "test_password", f"Expected 'test_password', got '{decrypted}'"

    def test_credential_update_persists(self):
        """Test that updating a credential persists the NEW value."""
        # Save old value
        old_encrypted = encrypt_password("old_password")
        set_credential(self.TEST_KEY, old_encrypted)

        # Verify old value saved
        loaded = get_credential(self.TEST_KEY)
        assert decrypt_password(loaded) == "old_password"

        # Update to new value
        new_encrypted = encrypt_password("new_password")
        set_credential(self.TEST_KEY, new_encrypted)

        # Verify NEW value is returned
        loaded_after = get_credential(self.TEST_KEY)
        decrypted = decrypt_password(loaded_after)
        assert decrypted == "new_password", f"Expected 'new_password', got '{decrypted}'"
