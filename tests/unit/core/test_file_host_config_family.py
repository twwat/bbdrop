"""Unit tests for host family helpers."""
import pytest

from src.core.file_host_config import (
    get_host_family,
    get_family_members,
    select_primary,
)


class TestGetHostFamily:
    def test_k2s_members_return_k2s(self):
        assert get_host_family("keep2share") == "k2s"
        assert get_host_family("fileboom") == "k2s"
        assert get_host_family("tezfiles") == "k2s"

    def test_non_family_host_returns_none(self):
        assert get_host_family("rapidgator") is None
        assert get_host_family("katfile") is None
        assert get_host_family("filedot") is None

    def test_unknown_host_returns_none(self):
        assert get_host_family("nonsense_host_id") is None


class TestGetFamilyMembers:
    def test_k2s_returns_priority_ordered_list(self):
        assert get_family_members("k2s") == ["keep2share", "fileboom", "tezfiles"]

    def test_unknown_family_returns_empty_list(self):
        assert get_family_members("nonexistent") == []

    def test_returned_list_is_a_copy(self):
        members = get_family_members("k2s")
        members.append("zzz")
        assert get_family_members("k2s") == ["keep2share", "fileboom", "tezfiles"]


class TestSelectPrimary:
    def test_highest_priority_enabled_wins(self):
        assert select_primary("k2s", {"keep2share", "fileboom", "tezfiles"}) == "keep2share"

    def test_skips_disabled_winner(self):
        assert select_primary("k2s", {"fileboom", "tezfiles"}) == "fileboom"

    def test_last_in_chain_when_only_tail_enabled(self):
        assert select_primary("k2s", {"tezfiles"}) == "tezfiles"

    def test_empty_enabled_set_returns_none(self):
        assert select_primary("k2s", set()) is None

    def test_ignores_unknown_hosts_in_enabled_set(self):
        assert select_primary("k2s", {"rapidgator", "fileboom"}) == "fileboom"

    def test_unknown_family_returns_none(self):
        assert select_primary("nonexistent_family", {"keep2share"}) is None
