"""Tests for github_api.py — GitHub REST API client."""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture()
def github_api():
    """Create a GitHubAPI instance without touching Vault or network."""
    with patch("github_api.VaultSecretManager") as MockVault:
        mock_mgr = MagicMock()
        mock_mgr.get_github_token.return_value = "fake-token"
        MockVault.return_value = mock_mgr

        from github_api import GitHubAPI
        api = GitHubAPI(token="fake-token")
        return api


class TestGitHubAPIInit:
    def test_authenticated_header(self, github_api):
        assert "Authorization" in github_api.session.headers
        assert github_api.session.headers["Authorization"] == "token fake-token"

    def test_user_agent(self, github_api):
        assert github_api.session.headers["User-Agent"] == "playwright-screenshot-app"

    def test_accept_header(self, github_api):
        assert "application/vnd.github.v3+json" in github_api.session.headers["Accept"]

    def test_unauthenticated(self):
        with patch("github_api.VaultSecretManager") as MockVault:
            mock_mgr = MagicMock()
            mock_mgr.get_github_token.return_value = None
            MockVault.return_value = mock_mgr
            from github_api import GitHubAPI
            api = GitHubAPI(token=None)
            assert "Authorization" not in api.session.headers


class TestGetUserProfile:
    def test_parses_profile(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "login": "octocat", "name": "The Octocat",
            "avatar_url": "https://avatars.example/octocat",
            "html_url": "https://github.com/octocat",
            "bio": "Hi there", "company": "@github",
            "location": "SF", "blog": "https://blog.example",
            "email": None, "twitter_username": None,
            "public_repos": 10, "public_gists": 5,
            "followers": 100, "following": 50,
            "created_at": "2011-01-25T18:44:36Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            profile = github_api.get_user_profile("octocat")

        assert profile["login"] == "octocat"
        assert profile["name"] == "The Octocat"
        assert profile["followers"] == 100
        assert profile["public_repos"] == 10

    def test_missing_optional_fields(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"login": "minimal"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            profile = github_api.get_user_profile("minimal")

        assert profile["login"] == "minimal"
        assert profile["name"] is None
        assert profile["bio"] is None


class TestGetUserRepos:
    def test_parses_repos(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "name": "repo1", "full_name": "user/repo1",
                "description": "A repo", "html_url": "https://github.com/user/repo1",
                "language": "Python", "stargazers_count": 42,
                "forks_count": 10, "open_issues_count": 3,
                "watchers_count": 42, "created_at": "2020-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "pushed_at": "2024-01-01T00:00:00Z",
                "topics": ["ml"], "fork": False, "archived": False,
                "homepage": None, "size": 1024, "default_branch": "main",
            },
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            repos = github_api.get_user_repos("user", sort="stars", per_page=10, page=1)

        assert len(repos) == 1
        assert repos[0]["name"] == "repo1"
        assert repos[0]["stargazers_count"] == 42
        assert repos[0]["topics"] == ["ml"]

    def test_empty_repos(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            repos = github_api.get_user_repos("newuser")

        assert repos == []


class TestGetRepoDetails:
    def test_parses_details(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "name": "myrepo", "full_name": "user/myrepo",
            "description": "desc", "html_url": "https://github.com/user/myrepo",
            "language": "Go", "stargazers_count": 999,
            "forks_count": 50, "open_issues_count": 7,
            "watchers_count": 999, "subscribers_count": 100,
            "topics": ["api"], "license": {"spdx_id": "MIT"},
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "homepage": "https://myrepo.dev",
            "default_branch": "main",
            "has_wiki": True, "has_pages": False, "archived": False,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            details = github_api.get_repo_details("user", "myrepo")

        assert details["name"] == "myrepo"
        assert details["license"] == "MIT"
        assert details["subscribers_count"] == 100

    def test_no_license(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"name": "nolicense", "license": None}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            details = github_api.get_repo_details("user", "nolicense")

        assert details["license"] is None


class TestGetUserEvents:
    def test_parses_events(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"type": "PushEvent", "repo": {"name": "user/repo"}, "created_at": "2024-01-01T00:00:00Z"},
            {"type": "WatchEvent", "repo": {"name": "other/repo"}, "created_at": "2024-01-02T00:00:00Z"},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            events = github_api.get_user_events("user")

        assert len(events) == 2
        assert events[0]["type"] == "PushEvent"
        assert events[0]["repo"] == "user/repo"


class TestGetRateLimit:
    def test_parses_rate_limit(self, github_api):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "resources": {
                "core": {"limit": 5000, "remaining": 4999, "reset": 1704067200}
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(github_api.session, "get", return_value=mock_resp):
            rate = github_api.get_rate_limit()

        assert rate["limit"] == 5000
        assert rate["remaining"] == 4999
        assert "reset" in rate


class TestHTTPErrors:
    def test_api_error_propagates(self, github_api):
        import requests
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404")

        with patch.object(github_api.session, "get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                github_api.get_user_profile("nonexistent")
