"""Tests for vault_manager.py — Secret management with Vault + local fallback."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest


@pytest.fixture()
def vault_mgr(tmp_path, monkeypatch):
    """Create a VaultSecretManager with all external deps disabled."""
    monkeypatch.setenv("VAULT_SECRET_FILE", str(tmp_path / "vault-token"))
    monkeypatch.setenv("K8S_SA_TOKEN_PATH", str(tmp_path / "sa-token"))
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with patch("vault_manager.hvac", create=True):
        with patch("vault_manager.HVAC_AVAILABLE", True):
            # Prevent actual Vault connection
            with patch("vault_manager.VaultSecretManager._init_vault"):
                from vault_manager import VaultSecretManager
                mgr = VaultSecretManager.__new__(VaultSecretManager)
                mgr.vault_addr = "http://mock:8200"
                mgr.vault_token = None
                mgr.vault_role = "playwright-screenshot"
                mgr.vault_client = None
                # Point local storage to tmp
                mgr.LOCAL_SECRET_DIR = tmp_path / ".playwright-screenshot"
                mgr.LOCAL_SECRET_FILE = mgr.LOCAL_SECRET_DIR / "secrets.enc"
                mgr.VAULT_FILE_PATH = Path(str(tmp_path / "vault-token"))
                mgr.K8S_SA_TOKEN_PATH = Path(str(tmp_path / "sa-token"))
                return mgr


# ═══════════════════════════════════════════════════════════════════════
#  Token priority chain
# ═══════════════════════════════════════════════════════════════════════

class TestTokenPriority:
    def test_vault_file_first(self, vault_mgr, tmp_path):
        """Vault Agent file has highest priority."""
        vault_mgr.VAULT_FILE_PATH.write_text("ghp_from_vault_file")
        token = vault_mgr.get_github_token()
        assert token == "ghp_from_vault_file"

    def test_vault_file_json_format(self, vault_mgr):
        """Vault Agent can write JSON with github_token key."""
        vault_mgr.VAULT_FILE_PATH.write_text(json.dumps({"github_token": "ghp_json_token"}))
        token = vault_mgr.get_github_token()
        assert token == "ghp_json_token"

    def test_env_var_fallback(self, vault_mgr, monkeypatch):
        """GITHUB_TOKEN env var is used when Vault sources are unavailable."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
        token = vault_mgr.get_github_token()
        assert token == "ghp_from_env"

    def test_local_file_fallback(self, vault_mgr):
        """Local encrypted file is the last resort."""
        # First store a token locally
        vault_mgr._local_store("ghp_local_token")
        token = vault_mgr.get_github_token()
        assert token == "ghp_local_token"

    def test_none_when_nothing_available(self, vault_mgr):
        token = vault_mgr.get_github_token()
        assert token is None

    def test_vault_file_overrides_env(self, vault_mgr, monkeypatch):
        """Vault file should beat environment variable."""
        vault_mgr.VAULT_FILE_PATH.write_text("ghp_file_wins")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_env_loses")
        token = vault_mgr.get_github_token()
        assert token == "ghp_file_wins"


# ═══════════════════════════════════════════════════════════════════════
#  Local encrypted storage
# ═══════════════════════════════════════════════════════════════════════

class TestLocalStorage:
    def test_store_and_retrieve(self, vault_mgr):
        assert vault_mgr._local_store("ghp_roundtrip")
        token = vault_mgr._local_retrieve()
        assert token == "ghp_roundtrip"

    def test_file_permissions(self, vault_mgr):
        vault_mgr._local_store("ghp_perms")
        mode = vault_mgr.LOCAL_SECRET_FILE.stat().st_mode & 0o777
        assert mode == 0o600

    def test_delete(self, vault_mgr):
        vault_mgr._local_store("ghp_delete_me")
        assert vault_mgr.LOCAL_SECRET_FILE.exists()
        assert vault_mgr._local_delete()
        assert not vault_mgr.LOCAL_SECRET_FILE.exists()

    def test_delete_nonexistent(self, vault_mgr):
        assert vault_mgr._local_delete()

    def test_retrieve_nonexistent(self, vault_mgr):
        assert vault_mgr._local_retrieve() is None

    def test_overwrite(self, vault_mgr):
        vault_mgr._local_store("ghp_first")
        vault_mgr._local_store("ghp_second")
        assert vault_mgr._local_retrieve() == "ghp_second"


# ═══════════════════════════════════════════════════════════════════════
#  Vault file retrieval
# ═══════════════════════════════════════════════════════════════════════

class TestVaultFileRetrieval:
    def test_plain_text(self, vault_mgr):
        vault_mgr.VAULT_FILE_PATH.write_text("ghp_plain")
        assert vault_mgr._file_retrieve() == "ghp_plain"

    def test_json_format(self, vault_mgr):
        vault_mgr.VAULT_FILE_PATH.write_text('{"github_token": "ghp_json"}')
        assert vault_mgr._file_retrieve() == "ghp_json"

    def test_json_token_key(self, vault_mgr):
        vault_mgr.VAULT_FILE_PATH.write_text('{"token": "ghp_alt_key"}')
        assert vault_mgr._file_retrieve() == "ghp_alt_key"

    def test_empty_file(self, vault_mgr):
        vault_mgr.VAULT_FILE_PATH.write_text("")
        assert vault_mgr._file_retrieve() is None

    def test_missing_file(self, vault_mgr):
        assert vault_mgr._file_retrieve() is None

    def test_whitespace_stripped(self, vault_mgr):
        vault_mgr.VAULT_FILE_PATH.write_text("  ghp_trimmed  \n")
        assert vault_mgr._file_retrieve() == "ghp_trimmed"


# ═══════════════════════════════════════════════════════════════════════
#  Public API: store / delete
# ═══════════════════════════════════════════════════════════════════════

class TestStoreAndDelete:
    def test_store_empty_rejected(self, vault_mgr):
        assert vault_mgr.store_github_token("") is False

    def test_store_whitespace_rejected(self, vault_mgr):
        assert vault_mgr.store_github_token("   ") is False

    def test_store_falls_through_to_local(self, vault_mgr):
        """With no Vault client, store should use local file."""
        assert vault_mgr.store_github_token("ghp_store_local")
        assert vault_mgr._local_retrieve() == "ghp_store_local"

    def test_delete_both_backends(self, vault_mgr):
        vault_mgr._local_store("ghp_del")
        assert vault_mgr.delete_github_token()
        assert vault_mgr._local_retrieve() is None


# ═══════════════════════════════════════════════════════════════════════
#  get_status
# ═══════════════════════════════════════════════════════════════════════

class TestGetStatus:
    def test_status_structure(self, vault_mgr):
        status = vault_mgr.get_status()
        assert "vault" in status
        assert "vault_file" in status
        assert "environment" in status
        assert "local_file" in status
        assert "token_available" in status

    def test_hvac_installed_flag(self, vault_mgr):
        with patch("vault_manager.HVAC_AVAILABLE", True):
            status = vault_mgr.get_status()
            assert status["vault"]["hvac_installed"] is True

    def test_no_vault_client(self, vault_mgr):
        status = vault_mgr.get_status()
        assert status["vault"]["connected"] is False
