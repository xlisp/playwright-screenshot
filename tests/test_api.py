"""Tests for api.py — Flask REST API endpoints."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════
#  Helpers: generate_filename, validate_screenshot_params, _archive_files
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateFilename:
    def test_png_extension(self, app):
        from api import generate_filename
        name = generate_filename("https://example.com", "png")
        assert name.startswith("screenshot_")
        assert name.endswith(".png")

    def test_jpeg_extension(self, app):
        from api import generate_filename
        name = generate_filename("https://example.com", "jpeg")
        assert name.endswith(".jpeg")

    def test_unique_each_call(self, app):
        from api import generate_filename
        a = generate_filename("https://example.com")
        b = generate_filename("https://example.com")
        assert a != b

    def test_different_url_different_hash(self, app):
        from api import generate_filename
        a = generate_filename("https://a.com")
        b = generate_filename("https://b.com")
        # The url_hash part (chars 26..34) should differ
        assert a[20:28] != b[20:28]


class TestValidateScreenshotParams:
    def _validate(self, data):
        from api import validate_screenshot_params
        return validate_screenshot_params(data)

    def test_valid_minimal(self, app):
        params, errors = self._validate({"url": "https://example.com"})
        assert not errors
        assert params["url"] == "https://example.com"
        assert params["width"] == 1920
        assert params["height"] == 1080
        assert params["full_page"] is True

    def test_missing_url(self, app):
        _, errors = self._validate({})
        assert any("url" in e for e in errors)

    def test_url_no_scheme(self, app):
        _, errors = self._validate({"url": "example.com"})
        assert any("http" in e for e in errors)

    def test_width_out_of_range(self, app):
        _, errors = self._validate({"url": "https://x.com", "width": 10})
        assert any("width" in e for e in errors)

    def test_width_too_large(self, app):
        _, errors = self._validate({"url": "https://x.com", "width": 9999})
        assert any("width" in e for e in errors)

    def test_height_out_of_range(self, app):
        _, errors = self._validate({"url": "https://x.com", "height": 10})
        assert any("height" in e for e in errors)

    def test_wait_time_negative(self, app):
        _, errors = self._validate({"url": "https://x.com", "wait_time": -1})
        assert any("wait_time" in e for e in errors)

    def test_wait_time_too_large(self, app):
        _, errors = self._validate({"url": "https://x.com", "wait_time": 99999})
        assert any("wait_time" in e for e in errors)

    def test_timeout_too_small(self, app):
        _, errors = self._validate({"url": "https://x.com", "timeout": 100})
        assert any("timeout" in e for e in errors)

    def test_timeout_too_large(self, app):
        _, errors = self._validate({"url": "https://x.com", "timeout": 999999})
        assert any("timeout" in e for e in errors)

    def test_invalid_format(self, app):
        _, errors = self._validate({"url": "https://x.com", "format": "bmp"})
        assert any("format" in e for e in errors)

    def test_jpg_normalizes_to_jpeg(self, app):
        params, errors = self._validate({"url": "https://x.com", "format": "jpg"})
        assert not errors
        assert params["format"] == "jpeg"

    def test_full_page_string_true(self, app):
        params, _ = self._validate({"url": "https://x.com", "full_page": "yes"})
        assert params["full_page"] is True

    def test_full_page_string_false(self, app):
        params, _ = self._validate({"url": "https://x.com", "full_page": "false"})
        assert params["full_page"] is False

    def test_width_not_integer(self, app):
        _, errors = self._validate({"url": "https://x.com", "width": "abc"})
        assert any("width" in e and "integer" in e for e in errors)

    def test_multiple_errors(self, app):
        _, errors = self._validate({"width": 1, "height": 1})
        assert len(errors) >= 3  # url + width + height


class TestArchiveFiles:
    def test_archive_creates_layout(self, app, archive_dir, screenshots_dir):
        from api import _archive_files
        # Create a fake file
        html_file = screenshots_dir / "test.html"
        html_file.write_text("<html>test</html>")

        result = _archive_files("testuser", {"html": html_file})

        assert "timestamp" in result
        assert "archived" in result
        # Verify latest
        latest = archive_dir / "testuser" / "latest" / "profile.html"
        assert latest.exists()
        assert latest.read_text() == "<html>test</html>"
        # Verify history
        ts = result["timestamp"]
        history = archive_dir / "testuser" / "history" / ts / "profile.html"
        assert history.exists()
        # Verify meta.json
        meta = archive_dir / "testuser" / "latest" / "meta.json"
        assert meta.exists()
        meta_data = json.loads(meta.read_text())
        assert meta_data["username"] == "testuser"

    def test_archive_skips_missing_file(self, app, archive_dir):
        from api import _archive_files
        missing = Path("/nonexistent/file.html")
        result = _archive_files("testuser", {"html": missing})
        assert result["archived"] == {}

    def test_archive_multiple_files(self, app, archive_dir, screenshots_dir):
        from api import _archive_files
        html = screenshots_dir / "test.html"
        html.write_text("<html>")
        png = screenshots_dir / "test.png"
        png.write_bytes(b"\x89PNG")
        json_file = screenshots_dir / "test.json"
        json_file.write_text("{}")

        result = _archive_files("user2", {"html": html, "png": png, "json": json_file})
        assert "html" in result["archived"]
        assert "png" in result["archived"]
        assert "json" in result["archived"]


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint: /health
# ═══════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    def test_health_degraded_no_chrome(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        # /fake/chrome doesn't exist
        assert resp.status_code == 503
        assert data["status"] == "degraded"
        assert data["chrome_available"] is False
        assert "timestamp" in data

    def test_health_has_archive_info(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert "archive_writable" in data


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint: POST /screenshot
# ═══════════════════════════════════════════════════════════════════════

class TestScreenshotEndpoint:
    def test_missing_body(self, client):
        resp = client.post("/screenshot", content_type="application/json")
        assert resp.status_code == 400

    def test_validation_errors(self, client):
        resp = client.post("/screenshot", json={"url": "not-a-url"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "messages" in data

    @patch("api.take_screenshot")
    def test_success(self, mock_take, client, screenshots_dir):
        def fake_screenshot(**kwargs):
            Path(kwargs["output_path"]).write_bytes(b"\x89PNG fake")
            return True
        mock_take.side_effect = fake_screenshot

        resp = client.post("/screenshot", json={"url": "https://example.com"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert "filename" in data
        assert "download_url" in data
        assert data["file_size"] > 0

    @patch("api.take_screenshot", return_value=False)
    def test_screenshot_fails(self, mock_take, client):
        resp = client.post("/screenshot", json={"url": "https://example.com"})
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False

    @patch("api.take_screenshot", side_effect=RuntimeError("browser crashed"))
    def test_screenshot_exception(self, mock_take, client):
        resp = client.post("/screenshot", json={"url": "https://example.com"})
        assert resp.status_code == 500
        assert "browser crashed" in resp.get_json()["error"]


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint: GET/DELETE /screenshots
# ═══════════════════════════════════════════════════════════════════════

class TestScreenshotsCRUD:
    def test_list_empty(self, client):
        resp = client.get("/screenshots")
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] == 0

    def test_list_with_files(self, client, screenshots_dir):
        (screenshots_dir / "screenshot_20240101_000000_abc12345_def123.png").write_bytes(b"img")
        resp = client.get("/screenshots")
        data = resp.get_json()
        assert data["count"] == 1

    def test_download_not_found(self, client):
        resp = client.get("/screenshots/nonexistent.png")
        assert resp.status_code == 404

    def test_download_path_traversal(self, client):
        # Flask normalizes ../ in URL paths, so use a filename containing '..'
        resp = client.get("/screenshots/..%2Fapi.py")
        # Werkzeug rejects or normalizes this — either 400 or 404 is acceptable
        assert resp.status_code in (400, 404)

    def test_download_success(self, client, screenshots_dir):
        f = screenshots_dir / "test.png"
        f.write_bytes(b"\x89PNG")
        resp = client.get("/screenshots/test.png")
        assert resp.status_code == 200

    def test_delete_not_found(self, client):
        resp = client.delete("/screenshots/nonexistent.png")
        assert resp.status_code == 404

    def test_delete_path_traversal(self, client):
        resp = client.delete("/screenshots/..%2Fsomething")
        assert resp.status_code in (400, 404)

    def test_delete_success(self, client, screenshots_dir):
        f = screenshots_dir / "todelete.png"
        f.write_bytes(b"data")
        resp = client.delete("/screenshots/todelete.png")
        assert resp.status_code == 200
        assert not f.exists()


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint: /github/*
# ═══════════════════════════════════════════════════════════════════════

class TestGitHubEndpoints:
    @patch("api._get_github_api")
    def test_profile(self, mock_api_fn, client, sample_profile):
        mock_api = MagicMock()
        mock_api.get_user_profile.return_value = sample_profile
        mock_api_fn.return_value = mock_api

        resp = client.get("/github/octocat")
        data = resp.get_json()
        assert data["success"] is True
        assert data["profile"]["login"] == "octocat"

    @patch("api._get_github_api")
    def test_profile_error(self, mock_api_fn, client):
        mock_api = MagicMock()
        mock_api.get_user_profile.side_effect = Exception("404 Not Found")
        mock_api_fn.return_value = mock_api

        resp = client.get("/github/nonexistent")
        assert resp.status_code == 500

    @patch("api._get_github_api")
    def test_repos(self, mock_api_fn, client, sample_repos):
        mock_api = MagicMock()
        mock_api.get_user_repos.return_value = sample_repos
        mock_api_fn.return_value = mock_api

        resp = client.get("/github/octocat/repos?sort=stars&per_page=10")
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] == 2

    @patch("api._get_github_api")
    @patch("api.generate_html", return_value="<html>mock</html>")
    def test_page(self, mock_html, mock_api_fn, client, sample_profile, sample_repos, sample_events):
        mock_api = MagicMock()
        mock_api.get_user_profile.return_value = sample_profile
        mock_api.get_user_repos.return_value = sample_repos
        mock_api.get_user_events.return_value = sample_events
        mock_api_fn.return_value = mock_api

        resp = client.get("/github/octocat/page")
        assert resp.status_code == 200
        assert b"mock" in resp.data

    @patch("api.take_screenshot")
    @patch("api._get_github_api")
    @patch("api.generate_html", return_value="<html>mock</html>")
    def test_github_screenshot_success(self, mock_html, mock_api_fn, mock_take, client, screenshots_dir, sample_profile, sample_repos, sample_events):
        mock_api = MagicMock()
        mock_api.get_user_profile.return_value = sample_profile
        mock_api.get_user_repos.return_value = sample_repos
        mock_api.get_user_events.return_value = sample_events
        mock_api_fn.return_value = mock_api

        def fake_screenshot(**kwargs):
            Path(kwargs["output_path"]).write_bytes(b"\x89PNG")
            return True
        mock_take.side_effect = fake_screenshot

        resp = client.post("/github/octocat/screenshot", json={"width": 800})
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["success"] is True
        assert data["username"] == "octocat"
        assert "archive" in data


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint: /archive/*
# ═══════════════════════════════════════════════════════════════════════

class TestArchiveEndpoints:
    def test_list_users_empty(self, client):
        resp = client.get("/archive")
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] == 0

    def test_list_users_with_data(self, client, archive_dir):
        user_dir = archive_dir / "testuser" / "latest"
        user_dir.mkdir(parents=True)
        meta = {"generated_at": "2024-01-01T00:00:00", "files": {}}
        (user_dir / "meta.json").write_text(json.dumps(meta))
        (archive_dir / "testuser" / "history").mkdir()

        resp = client.get("/archive")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["users"][0]["username"] == "testuser"

    def test_list_snapshots_not_found(self, client):
        resp = client.get("/archive/nouser")
        assert resp.status_code == 404

    def test_list_snapshots_path_traversal(self, client):
        resp = client.get("/archive/..%2F..")
        assert resp.status_code == 400

    def test_list_snapshots(self, client, archive_dir):
        user_dir = archive_dir / "testuser"
        snap = user_dir / "history" / "20240101_000000"
        snap.mkdir(parents=True)
        (snap / "profile.html").write_text("<html>")
        (user_dir / "latest").mkdir(parents=True)

        resp = client.get("/archive/testuser")
        data = resp.get_json()
        assert data["success"] is True
        assert data["snapshot_count"] == 1

    def test_download_archived_file(self, client, archive_dir):
        latest = archive_dir / "testuser" / "latest"
        latest.mkdir(parents=True)
        (latest / "profile.html").write_text("<html>hello</html>")

        resp = client.get("/archive/testuser/latest/profile.html")
        assert resp.status_code == 200
        assert b"hello" in resp.data

    def test_download_path_traversal_blocked(self, client, archive_dir):
        resp = client.get("/archive/testuser/../../etc/passwd")
        assert resp.status_code == 400

    def test_download_not_found(self, client, archive_dir):
        (archive_dir / "testuser" / "latest").mkdir(parents=True)
        resp = client.get("/archive/testuser/latest/missing.png")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint: /vault/*
# ═══════════════════════════════════════════════════════════════════════

class TestVaultEndpoints:
    def test_vault_status(self, client):
        resp = client.get("/vault/status")
        data = resp.get_json()
        assert data["success"] is True
        assert "vault" in data

    def test_store_token(self, client):
        resp = client.post("/vault/token", json={"token": "ghp_test1234567890abcdef"})
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["success"] is True
        assert "masked" in data

    def test_store_empty_token(self, client):
        resp = client.post("/vault/token", json={"token": ""})
        assert resp.status_code == 400

    def test_store_missing_token(self, client):
        resp = client.post("/vault/token", json={})
        assert resp.status_code == 400

    def test_delete_token(self, client):
        resp = client.delete("/vault/token")
        data = resp.get_json()
        assert data["success"] is True


# ═══════════════════════════════════════════════════════════════════════
#  Error handlers
# ═══════════════════════════════════════════════════════════════════════

class TestErrorHandlers:
    def test_404(self, client):
        resp = client.get("/nonexistent-route")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False
