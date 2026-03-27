"""
Tests for engine.scripts.setup_hedera — the one-time Hedera setup script.

Covers the stub mode (when SDK is unavailable) which generates
a local wallets.json for development.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.scripts.setup_hedera import (
    NUM_ACCOUNTS,
    TOKENS_TO_CREATE,
    TOPICS_TO_CREATE,
    run_stub,
)


class TestRunStub:
    def test_creates_wallets_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_stub()
        assert (tmp_path / "wallets.json").exists()

    def test_creates_correct_number_of_wallets(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_stub()
        data = json.loads((tmp_path / "wallets.json").read_text())
        assert len(data) == NUM_ACCOUNTS

    def test_wallet_entries_have_required_keys(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_stub()
        data = json.loads((tmp_path / "wallets.json").read_text())
        for w in data:
            assert "index" in w
            assert "account_id" in w
            assert "private_key" in w
            assert "assigned" in w
            assert w["assigned"] is False

    def test_wallets_have_unique_account_ids(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_stub()
        data = json.loads((tmp_path / "wallets.json").read_text())
        ids = [w["account_id"] for w in data]
        assert len(ids) == len(set(ids))

    def test_wallets_have_sequential_indices(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_stub()
        data = json.loads((tmp_path / "wallets.json").read_text())
        indices = [w["index"] for w in data]
        assert indices == list(range(NUM_ACCOUNTS))


class TestConstants:
    def test_num_accounts_is_15(self):
        assert NUM_ACCOUNTS == 15

    def test_tokens_count(self):
        assert len(TOKENS_TO_CREATE) == 5

    def test_token_names(self):
        names = [t[0] for t in TOKENS_TO_CREATE]
        assert "ARENA" in names
        assert "wHBAR" in names
        assert "wBTC" in names
        assert "wETH" in names
        assert "wDOGE" in names

    def test_topics_count(self):
        assert len(TOPICS_TO_CREATE) == 2
