#!/usr/bin/env python3
"""
Playwright Screenshot REST API Service

Provides a REST API for taking screenshots of web pages,
GitHub profile viewing, and Vault-based secret management.

Endpoints:
    POST /screenshot           - Take a screenshot of a URL
    GET  /health               - Health check endpoint
    GET  /screenshots/<file>   - Download a screenshot
    GET  /screenshots          - List all screenshots
    DELETE /screenshots/<file> - Delete a screenshot

    GET  /github/<username>           - Get GitHub user profile
    GET  /github/<username>/repos     - Get user repositories
    GET  /github/<username>/page      - Generate HTML profile page
    POST /github/<username>/screenshot - Generate page + screenshot

    GET  /vault/status         - Vault backend status
    POST /vault/token          - Store GitHub token
    DELETE /vault/token        - Delete stored token

Usage:
    python api.py

Environment Variables:
    PORT          - Server port (default: 8080)
    CHROME_PATH   - Path to Chrome executable
    GITHUB_TOKEN  - GitHub API token (fallback)
    VAULT_ADDR    - HashiCorp Vault address
    VAULT_TOKEN   - HashiCorp Vault token
"""

import os
import sys
import uuid
import json
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, Response
from werkzeug.exceptions import HTTPException

from screenshot import take_screenshot, CHROME_PATH
from github_api import GitHubAPI
from github_page_generator import generate_html
from vault_manager import VaultSecretManager

# Configuration
PORT = int(os.environ.get('PORT', 8080))
SCREENSHOTS_DIR = Path(os.environ.get('SCREENSHOTS_DIR', '/app/screenshots'))
MAX_WIDTH = 3840
MAX_HEIGHT = 2160
MAX_TIMEOUT = 120000  # 2 minutes

# Ensure screenshots directory exists
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Flask app
app = Flask(__name__)

# Shared instances
vault_mgr = VaultSecretManager()


def generate_filename(url: str, extension: str = 'png') -> str:
    """Generate a unique filename based on URL and timestamp."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    unique_id = uuid.uuid4().hex[:6]
    return f"screenshot_{timestamp}_{url_hash}_{unique_id}.{extension}"


def validate_screenshot_params(data: dict) -> tuple[dict, list]:
    """Validate and normalize screenshot parameters."""
    errors = []
    params = {}

    url = data.get('url', '').strip()
    if not url:
        errors.append("'url' is required")
    elif not url.startswith(('http://', 'https://')):
        errors.append("'url' must start with http:// or https://")
    else:
        params['url'] = url

    width = data.get('width', 1920)
    try:
        width = int(width)
        if width < 320 or width > MAX_WIDTH:
            errors.append(f"'width' must be between 320 and {MAX_WIDTH}")
        else:
            params['width'] = width
    except (ValueError, TypeError):
        errors.append("'width' must be an integer")

    height = data.get('height', 1080)
    try:
        height = int(height)
        if height < 240 or height > MAX_HEIGHT:
            errors.append(f"'height' must be between 240 and {MAX_HEIGHT}")
        else:
            params['height'] = height
    except (ValueError, TypeError):
        errors.append("'height' must be an integer")

    full_page = data.get('full_page', True)
    if isinstance(full_page, str):
        full_page = full_page.lower() in ('true', '1', 'yes')
    params['full_page'] = bool(full_page)

    wait_time = data.get('wait_time', 3000)
    try:
        wait_time = int(wait_time)
        if wait_time < 0 or wait_time > 30000:
            errors.append("'wait_time' must be between 0 and 30000 milliseconds")
        else:
            params['wait_time'] = wait_time
    except (ValueError, TypeError):
        errors.append("'wait_time' must be an integer")

    timeout = data.get('timeout', 60000)
    try:
        timeout = int(timeout)
        if timeout < 5000 or timeout > MAX_TIMEOUT:
            errors.append(f"'timeout' must be between 5000 and {MAX_TIMEOUT} milliseconds")
        else:
            params['timeout'] = timeout
    except (ValueError, TypeError):
        errors.append("'timeout' must be an integer")

    fmt = data.get('format', 'png').lower()
    if fmt not in ('png', 'jpeg', 'jpg'):
        errors.append("'format' must be 'png' or 'jpeg'")
    else:
        params['format'] = 'jpeg' if fmt == 'jpg' else fmt

    return params, errors


# ═══════════════════════════════════════════════════════════════════════
#  Original Screenshot Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    chrome_exists = Path(CHROME_PATH).exists()
    return jsonify({
        'status': 'healthy' if chrome_exists else 'degraded',
        'chrome_path': CHROME_PATH,
        'chrome_available': chrome_exists,
        'screenshots_dir': str(SCREENSHOTS_DIR),
        'vault_connected': vault_mgr.vault_client is not None,
        'github_token_available': vault_mgr.get_github_token() is not None,
        'timestamp': datetime.now().isoformat()
    }), 200 if chrome_exists else 503


@app.route('/screenshot', methods=['POST'])
def create_screenshot():
    """Take a screenshot of a URL."""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()

    if not data:
        return jsonify({
            'success': False,
            'error': 'Request body is required',
            'message': 'Please provide JSON data with at least a "url" field'
        }), 400

    params, errors = validate_screenshot_params(data)
    if errors:
        return jsonify({'success': False, 'error': 'Validation failed', 'messages': errors}), 400

    filename = generate_filename(params['url'], params.get('format', 'png'))
    output_path = SCREENSHOTS_DIR / filename

    try:
        success = take_screenshot(
            url=params['url'],
            output_path=str(output_path),
            width=params.get('width', 1920),
            height=params.get('height', 1080),
            full_page=params.get('full_page', True),
            wait_time=params.get('wait_time', 3000),
            timeout=params.get('timeout', 60000)
        )
        if success and output_path.exists():
            file_size = output_path.stat().st_size
            return jsonify({
                'success': True, 'filename': filename,
                'url': params['url'],
                'download_url': f'/screenshots/{filename}',
                'file_size': file_size,
                'file_size_human': f'{file_size / 1024:.2f} KB',
                'settings': params,
                'timestamp': datetime.now().isoformat()
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Screenshot failed'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': 'Internal error', 'message': str(e)}), 500


@app.route('/screenshots/<filename>', methods=['GET'])
def download_screenshot(filename: str):
    """Download a screenshot file."""
    if '..' in filename or '/' in filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    file_path = SCREENSHOTS_DIR / filename
    if not file_path.exists():
        return jsonify({'success': False, 'error': 'File not found'}), 404
    mimetype = 'image/png' if filename.endswith('.png') else 'image/jpeg'
    return send_file(file_path, mimetype=mimetype, as_attachment=False, download_name=filename)


@app.route('/screenshots', methods=['GET'])
def list_screenshots():
    """List all available screenshots."""
    files = []
    for f in SCREENSHOTS_DIR.glob('screenshot_*'):
        if f.is_file():
            stat = f.stat()
            files.append({
                'filename': f.name,
                'download_url': f'/screenshots/{f.name}',
                'size': stat.st_size,
                'size_human': f'{stat.st_size / 1024:.2f} KB',
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
    files.sort(key=lambda x: x['created'], reverse=True)
    return jsonify({'success': True, 'count': len(files), 'screenshots': files}), 200


@app.route('/screenshots/<filename>', methods=['DELETE'])
def delete_screenshot(filename: str):
    """Delete a screenshot file."""
    if '..' in filename or '/' in filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    file_path = SCREENSHOTS_DIR / filename
    if not file_path.exists():
        return jsonify({'success': False, 'error': 'File not found'}), 404
    try:
        file_path.unlink()
        return jsonify({'success': True, 'message': f'Screenshot "{filename}" deleted'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
#  GitHub API Endpoints
# ═══════════════════════════════════════════════════════════════════════


def _get_github_api() -> GitHubAPI:
    """Create a GitHubAPI instance using Vault-managed token."""
    return GitHubAPI()


@app.route('/github/<username>', methods=['GET'])
def github_profile(username: str):
    """Get a GitHub user's profile information."""
    try:
        api = _get_github_api()
        profile = api.get_user_profile(username)
        return jsonify({'success': True, 'profile': profile}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/github/<username>/repos', methods=['GET'])
def github_repos(username: str):
    """Get a GitHub user's repositories."""
    sort = request.args.get('sort', 'updated')
    per_page = min(int(request.args.get('per_page', 30)), 100)
    page = int(request.args.get('page', 1))
    try:
        api = _get_github_api()
        repos = api.get_user_repos(username, sort=sort, per_page=per_page, page=page)
        return jsonify({'success': True, 'count': len(repos), 'repos': repos}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/github/<username>/page', methods=['GET'])
def github_page(username: str):
    """
    Generate and return an HTML profile page for the GitHub user.
    Returns HTML directly (Content-Type: text/html).
    """
    try:
        api = _get_github_api()
        profile = api.get_user_profile(username)
        repos = api.get_user_repos(username, per_page=30)
        events = api.get_user_events(username)
        html = generate_html(profile, repos, events)
        return Response(html, mimetype='text/html')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/github/<username>/screenshot', methods=['POST'])
def github_screenshot(username: str):
    """
    Generate an HTML profile page for the GitHub user, save it,
    take a screenshot, and return both files.

    Optional JSON body:
        { "width": 1280, "height": 900, "full_page": true }
    """
    data = request.get_json(silent=True) or {}
    width = int(data.get('width', 1280))
    height = int(data.get('height', 900))
    full_page = data.get('full_page', True)

    try:
        api = _get_github_api()
        profile = api.get_user_profile(username)
        repos = api.get_user_repos(username, per_page=30)
        events = api.get_user_events(username)
        html = generate_html(profile, repos, events)

        # Save HTML
        html_filename = f"github_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        html_path = SCREENSHOTS_DIR / html_filename
        html_path.write_text(html)

        # Take screenshot of the generated HTML
        png_filename = html_filename.replace('.html', '.png')
        png_path = SCREENSHOTS_DIR / png_filename
        file_url = f"file://{html_path.resolve()}"

        success = take_screenshot(
            url=file_url,
            output_path=str(png_path),
            width=width, height=height,
            full_page=full_page,
            wait_time=1000, timeout=30000,
        )

        if success and png_path.exists():
            file_size = png_path.stat().st_size
            return jsonify({
                'success': True,
                'username': username,
                'html_file': html_filename,
                'html_url': f'/screenshots/{html_filename}',
                'screenshot_file': png_filename,
                'screenshot_url': f'/screenshots/{png_filename}',
                'file_size': file_size,
                'file_size_human': f'{file_size / 1024:.2f} KB',
                'timestamp': datetime.now().isoformat(),
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Screenshot failed',
                'html_file': html_filename,
                'html_url': f'/screenshots/{html_filename}',
            }), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
#  Vault / Secret Management Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.route('/vault/status', methods=['GET'])
def vault_status():
    """Get Vault and secret backend status."""
    status = vault_mgr.get_status()
    return jsonify({'success': True, **status}), 200


@app.route('/vault/token', methods=['POST'])
def vault_store_token():
    """
    Store a GitHub API token.

    JSON body: { "token": "ghp_xxxx..." }
    """
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()
    if not token:
        return jsonify({'success': False, 'error': "'token' is required"}), 400
    ok = vault_mgr.store_github_token(token)
    if ok:
        masked = token[:4] + '•' * (len(token) - 8) + token[-4:]
        return jsonify({'success': True, 'message': 'Token stored', 'masked': masked}), 201
    return jsonify({'success': False, 'error': 'Failed to store token'}), 500


@app.route('/vault/token', methods=['DELETE'])
def vault_delete_token():
    """Delete stored GitHub token from all backends."""
    ok = vault_mgr.delete_github_token()
    return jsonify({'success': ok}), 200 if ok else 500


# ═══════════════════════════════════════════════════════════════════════
#  Error Handlers
# ═══════════════════════════════════════════════════════════════════════


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    return jsonify({'success': False, 'error': e.name, 'message': e.description}), e.code


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({'success': False, 'error': 'Internal Server Error', 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"🚀 Playwright Screenshot API Server")
    print(f"================================")
    print(f"Port: {PORT}")
    print(f"Chrome: {CHROME_PATH}")
    print(f"Screenshots: {SCREENSHOTS_DIR}")
    print(f"================================")
    print(f"Endpoints:")
    print(f"  POST /screenshot                  - Take a screenshot")
    print(f"  GET  /screenshots                 - List all screenshots")
    print(f"  GET  /screenshots/<f>             - Download a screenshot")
    print(f"  DELETE /screenshots/<f>           - Delete a screenshot")
    print(f"  GET  /health                      - Health check")
    print(f"  ── GitHub ──")
    print(f"  GET  /github/<user>               - User profile")
    print(f"  GET  /github/<user>/repos         - User repositories")
    print(f"  GET  /github/<user>/page          - Generated HTML page")
    print(f"  POST /github/<user>/screenshot    - HTML + screenshot")
    print(f"  ── Vault ──")
    print(f"  GET  /vault/status                - Secret backend status")
    print(f"  POST /vault/token                 - Store GitHub token")
    print(f"  DELETE /vault/token               - Delete GitHub token")
    print(f"================================")

    app.run(host='0.0.0.0', port=PORT, debug=False)
