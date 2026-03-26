"""Shared fixtures for playwright-screenshot tests."""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Patch heavy imports before they touch the network / filesystem ────

@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    """Redirect all data dirs to tmp_path so tests never touch real paths."""
    screenshots = tmp_path / "screenshots"
    archive = tmp_path / "archive"
    screenshots.mkdir()
    archive.mkdir()
    monkeypatch.setenv("SCREENSHOTS_DIR", str(screenshots))
    monkeypatch.setenv("ARCHIVE_DIR", str(archive))
    monkeypatch.setenv("CHROME_PATH", "/fake/chrome")
    # Prevent Vault from connecting
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


@pytest.fixture()
def mock_vault_manager():
    """Return a mock VaultSecretManager that doesn't connect to anything."""
    with patch("vault_manager.VaultSecretManager") as MockCls:
        instance = MagicMock()
        instance.vault_client = None
        instance.get_github_token.return_value = None
        instance.get_status.return_value = {
            "vault": {"hvac_installed": True, "connected": False, "address": "mock", "k8s_role": "mock", "k8s_sa_token_exists": False},
            "vault_file": {"path": "/vault/secrets/github-token", "exists": False},
            "environment": {"GITHUB_TOKEN": "not set", "VAULT_ADDR": "not set", "VAULT_TOKEN": "not set"},
            "local_file": {"path": "/tmp/secrets.enc", "exists": False},
            "token_available": False,
        }
        instance.store_github_token.return_value = True
        instance.delete_github_token.return_value = True
        MockCls.return_value = instance
        yield instance


@pytest.fixture()
def app(tmp_path, mock_vault_manager):
    """Create a Flask test app with isolated directories."""
    screenshots = tmp_path / "screenshots"
    archive = tmp_path / "archive"
    screenshots.mkdir(exist_ok=True)
    archive.mkdir(exist_ok=True)

    # Patch module-level constants before importing
    with patch.dict(os.environ, {
        "SCREENSHOTS_DIR": str(screenshots),
        "ARCHIVE_DIR": str(archive),
        "CHROME_PATH": "/fake/chrome",
    }):
        # We need to reload api module so it picks up the patched env + VaultSecretManager
        import importlib
        with patch("api.VaultSecretManager", return_value=mock_vault_manager):
            import api
            api.SCREENSHOTS_DIR = screenshots
            api.ARCHIVE_DIR = archive
            api.vault_mgr = mock_vault_manager
            api.app.config["TESTING"] = True
            yield api.app


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def screenshots_dir(app):
    """Return the isolated screenshots directory."""
    import api
    return api.SCREENSHOTS_DIR


@pytest.fixture()
def archive_dir(app):
    """Return the isolated archive directory."""
    import api
    return api.ARCHIVE_DIR


# ── Sample data fixtures ─────────────────────────────────────────────

@pytest.fixture()
def sample_profile():
    return {
        "login": "octocat",
        "name": "The Octocat",
        "avatar_url": "https://avatars.githubusercontent.com/u/583231",
        "html_url": "https://github.com/octocat",
        "bio": "GitHub mascot",
        "company": "@github",
        "location": "San Francisco",
        "blog": "https://github.blog",
        "email": None,
        "twitter_username": None,
        "public_repos": 8,
        "public_gists": 8,
        "followers": 10000,
        "following": 9,
        "created_at": "2011-01-25T18:44:36Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture()
def sample_repos():
    return [
        {
            "name": "Hello-World",
            "full_name": "octocat/Hello-World",
            "description": "My first repository on GitHub!",
            "html_url": "https://github.com/octocat/Hello-World",
            "language": "Python",
            "stargazers_count": 2500,
            "forks_count": 1800,
            "open_issues_count": 100,
            "watchers_count": 2500,
            "created_at": "2011-01-26T19:01:12Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "topics": ["hello", "world"],
            "fork": False,
            "archived": False,
            "homepage": "https://example.com",
            "size": 1024,
            "default_branch": "main",
        },
        {
            "name": "Spoon-Knife",
            "full_name": "octocat/Spoon-Knife",
            "description": "A fork demo",
            "html_url": "https://github.com/octocat/Spoon-Knife",
            "language": "JavaScript",
            "stargazers_count": 12000,
            "forks_count": 140000,
            "open_issues_count": 50,
            "watchers_count": 12000,
            "created_at": "2011-01-27T19:30:43Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "topics": ["demo"],
            "fork": True,
            "archived": False,
            "homepage": None,
            "size": 512,
            "default_branch": "main",
        },
    ]


@pytest.fixture()
def sample_events():
    return [
        {"type": "PushEvent", "repo": "octocat/Hello-World", "created_at": "2024-01-01T10:00:00Z"},
        {"type": "CreateEvent", "repo": "octocat/new-repo", "created_at": "2024-01-01T09:00:00Z"},
    ]
