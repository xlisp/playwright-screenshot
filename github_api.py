#!/usr/bin/env python3
"""
GitHub API Client

Fetches user profiles and repository information from the GitHub API.
Integrates with VaultSecretManager for token management.

Usage:
    from github_api import GitHubAPI
    api = GitHubAPI()
    profile = api.get_user_profile("octocat")
    repos = api.get_user_repos("octocat")
"""

import os
import requests
from datetime import datetime
from vault_manager import VaultSecretManager


class GitHubAPI:
    """GitHub REST API v3 client with Vault-backed authentication."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None):
        self.secret_mgr = VaultSecretManager()
        self.token = token or self.secret_mgr.get_github_token()
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "playwright-screenshot-app",
        })
        if self.token:
            self.session.headers["Authorization"] = f"token {self.token}"
            print("✅ GitHub API: authenticated")
        else:
            print("⚠️  GitHub API: unauthenticated (rate limit 60 req/hr)")

    # ── Core API Methods ──────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        """Make a GET request to GitHub API."""
        url = f"{self.BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_user_profile(self, username: str) -> dict:
        """
        Get a user's GitHub profile.

        Returns dict with: login, name, avatar_url, bio, company,
        location, blog, public_repos, public_gists, followers,
        following, created_at, etc.
        """
        data = self._get(f"/users/{username}")
        return {
            "login": data.get("login"),
            "name": data.get("name"),
            "avatar_url": data.get("avatar_url"),
            "html_url": data.get("html_url"),
            "bio": data.get("bio"),
            "company": data.get("company"),
            "location": data.get("location"),
            "blog": data.get("blog"),
            "email": data.get("email"),
            "twitter_username": data.get("twitter_username"),
            "public_repos": data.get("public_repos"),
            "public_gists": data.get("public_gists"),
            "followers": data.get("followers"),
            "following": data.get("following"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def get_user_repos(
        self,
        username: str,
        sort: str = "updated",
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict]:
        """
        Get a user's public repositories.

        Args:
            username: GitHub username
            sort: Sort field (created, updated, pushed, full_name)
            per_page: Results per page (max 100)
            page: Page number

        Returns list of repo dicts with: name, description, language,
        stars, forks, html_url, etc.
        """
        data = self._get(
            f"/users/{username}/repos",
            params={"sort": sort, "per_page": per_page, "page": page},
        )
        repos = []
        for repo in data:
            repos.append({
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "html_url": repo.get("html_url"),
                "language": repo.get("language"),
                "stargazers_count": repo.get("stargazers_count", 0),
                "forks_count": repo.get("forks_count", 0),
                "open_issues_count": repo.get("open_issues_count", 0),
                "watchers_count": repo.get("watchers_count", 0),
                "created_at": repo.get("created_at"),
                "updated_at": repo.get("updated_at"),
                "pushed_at": repo.get("pushed_at"),
                "topics": repo.get("topics", []),
                "fork": repo.get("fork", False),
                "archived": repo.get("archived", False),
                "homepage": repo.get("homepage"),
                "size": repo.get("size", 0),
                "default_branch": repo.get("default_branch"),
            })
        return repos

    def get_repo_details(self, owner: str, repo: str) -> dict:
        """Get detailed information about a specific repository."""
        data = self._get(f"/repos/{owner}/{repo}")
        return {
            "name": data.get("name"),
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "html_url": data.get("html_url"),
            "language": data.get("language"),
            "stargazers_count": data.get("stargazers_count", 0),
            "forks_count": data.get("forks_count", 0),
            "open_issues_count": data.get("open_issues_count", 0),
            "watchers_count": data.get("watchers_count", 0),
            "subscribers_count": data.get("subscribers_count", 0),
            "topics": data.get("topics", []),
            "license": data.get("license", {}).get("spdx_id") if data.get("license") else None,
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "homepage": data.get("homepage"),
            "default_branch": data.get("default_branch"),
            "has_wiki": data.get("has_wiki"),
            "has_pages": data.get("has_pages"),
            "archived": data.get("archived"),
        }

    def get_user_events(self, username: str, per_page: int = 10) -> list[dict]:
        """Get recent public events for a user."""
        data = self._get(
            f"/users/{username}/events/public",
            params={"per_page": per_page},
        )
        events = []
        for evt in data:
            events.append({
                "type": evt.get("type"),
                "repo": evt.get("repo", {}).get("name"),
                "created_at": evt.get("created_at"),
            })
        return events

    def get_rate_limit(self) -> dict:
        """Get current API rate limit status."""
        data = self._get("/rate_limit")
        core = data.get("resources", {}).get("core", {})
        return {
            "limit": core.get("limit"),
            "remaining": core.get("remaining"),
            "reset": datetime.fromtimestamp(
                core.get("reset", 0)
            ).isoformat(),
        }


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="GitHub API Client")
    parser.add_argument("username", help="GitHub username")
    parser.add_argument("--repos", action="store_true", help="List repositories")
    parser.add_argument("--repo", help="Get specific repo details (repo name)")
    parser.add_argument("--events", action="store_true", help="Show recent events")
    parser.add_argument("--rate", action="store_true", help="Show rate limit")
    parser.add_argument("--token", help="GitHub token (overrides Vault)")

    args = parser.parse_args()
    api = GitHubAPI(token=args.token)

    if args.rate:
        print(json.dumps(api.get_rate_limit(), indent=2))
    elif args.repo:
        print(json.dumps(api.get_repo_details(args.username, args.repo), indent=2))
    elif args.repos:
        repos = api.get_user_repos(args.username)
        print(json.dumps(repos, indent=2))
    elif args.events:
        print(json.dumps(api.get_user_events(args.username), indent=2))
    else:
        profile = api.get_user_profile(args.username)
        print(json.dumps(profile, indent=2))
