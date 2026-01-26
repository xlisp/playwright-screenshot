#!/usr/bin/env python3
"""
Playwright Screenshot REST API Service

Provides a REST API for taking screenshots of web pages.

Endpoints:
    POST /screenshot - Take a screenshot of a URL
    GET /health - Health check endpoint
    GET /screenshots/<filename> - Download a screenshot

Usage:
    python api.py
    
Environment Variables:
    PORT - Server port (default: 8080)
    CHROME_PATH - Path to Chrome executable
"""

import os
import sys
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from werkzeug.exceptions import HTTPException

from screenshot import take_screenshot, CHROME_PATH

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
    
    # URL (required)
    url = data.get('url', '').strip()
    if not url:
        errors.append("'url' is required")
    elif not url.startswith(('http://', 'https://')):
        errors.append("'url' must start with http:// or https://")
    else:
        params['url'] = url
    
    # Width (optional)
    width = data.get('width', 1920)
    try:
        width = int(width)
        if width < 320 or width > MAX_WIDTH:
            errors.append(f"'width' must be between 320 and {MAX_WIDTH}")
        else:
            params['width'] = width
    except (ValueError, TypeError):
        errors.append("'width' must be an integer")
    
    # Height (optional)
    height = data.get('height', 1080)
    try:
        height = int(height)
        if height < 240 or height > MAX_HEIGHT:
            errors.append(f"'height' must be between 240 and {MAX_HEIGHT}")
        else:
            params['height'] = height
    except (ValueError, TypeError):
        errors.append("'height' must be an integer")
    
    # Full page (optional)
    full_page = data.get('full_page', True)
    if isinstance(full_page, str):
        full_page = full_page.lower() in ('true', '1', 'yes')
    params['full_page'] = bool(full_page)
    
    # Wait time (optional)
    wait_time = data.get('wait_time', 3000)
    try:
        wait_time = int(wait_time)
        if wait_time < 0 or wait_time > 30000:
            errors.append("'wait_time' must be between 0 and 30000 milliseconds")
        else:
            params['wait_time'] = wait_time
    except (ValueError, TypeError):
        errors.append("'wait_time' must be an integer")
    
    # Timeout (optional)
    timeout = data.get('timeout', 60000)
    try:
        timeout = int(timeout)
        if timeout < 5000 or timeout > MAX_TIMEOUT:
            errors.append(f"'timeout' must be between 5000 and {MAX_TIMEOUT} milliseconds")
        else:
            params['timeout'] = timeout
    except (ValueError, TypeError):
        errors.append("'timeout' must be an integer")
    
    # Format (optional)
    fmt = data.get('format', 'png').lower()
    if fmt not in ('png', 'jpeg', 'jpg'):
        errors.append("'format' must be 'png' or 'jpeg'")
    else:
        params['format'] = 'jpeg' if fmt == 'jpg' else fmt
    
    return params, errors


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    chrome_exists = Path(CHROME_PATH).exists()
    return jsonify({
        'status': 'healthy' if chrome_exists else 'degraded',
        'chrome_path': CHROME_PATH,
        'chrome_available': chrome_exists,
        'screenshots_dir': str(SCREENSHOTS_DIR),
        'timestamp': datetime.now().isoformat()
    }), 200 if chrome_exists else 503


@app.route('/screenshot', methods=['POST'])
def create_screenshot():
    """
    Take a screenshot of a URL.
    
    Request JSON:
        {
            "url": "https://example.com",  # Required
            "width": 1920,                  # Optional, default 1920
            "height": 1080,                 # Optional, default 1080
            "full_page": true,              # Optional, default true
            "wait_time": 3000,              # Optional, milliseconds, default 3000
            "timeout": 60000,               # Optional, milliseconds, default 60000
            "format": "png"                 # Optional, 'png' or 'jpeg', default 'png'
        }
    
    Response JSON:
        {
            "success": true,
            "filename": "screenshot_20240101_120000_abc123_def456.png",
            "url": "https://example.com",
            "download_url": "/screenshots/screenshot_20240101_120000_abc123_def456.png",
            "file_size": 123456,
            "settings": {...}
        }
    """
    # Parse request data
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
    
    # Validate parameters
    params, errors = validate_screenshot_params(data)
    
    if errors:
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'messages': errors
        }), 400
    
    # Generate output filename
    filename = generate_filename(params['url'], params.get('format', 'png'))
    output_path = SCREENSHOTS_DIR / filename
    
    # Take screenshot
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
                'success': True,
                'filename': filename,
                'url': params['url'],
                'download_url': f'/screenshots/{filename}',
                'file_size': file_size,
                'file_size_human': f'{file_size / 1024:.2f} KB',
                'settings': {
                    'width': params.get('width', 1920),
                    'height': params.get('height', 1080),
                    'full_page': params.get('full_page', True),
                    'wait_time': params.get('wait_time', 3000),
                    'timeout': params.get('timeout', 60000),
                    'format': params.get('format', 'png')
                },
                'timestamp': datetime.now().isoformat()
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Screenshot failed',
                'message': 'Failed to capture screenshot. The URL may be inaccessible or timed out.'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal error',
            'message': str(e)
        }), 500


@app.route('/screenshots/<filename>', methods=['GET'])
def download_screenshot(filename: str):
    """Download a screenshot file."""
    # Security: prevent path traversal
    if '..' in filename or '/' in filename:
        return jsonify({
            'success': False,
            'error': 'Invalid filename'
        }), 400
    
    file_path = SCREENSHOTS_DIR / filename
    
    if not file_path.exists():
        return jsonify({
            'success': False,
            'error': 'File not found',
            'message': f'Screenshot "{filename}" does not exist'
        }), 404
    
    # Determine mimetype
    mimetype = 'image/png' if filename.endswith('.png') else 'image/jpeg'
    
    return send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=False,
        download_name=filename
    )


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
    
    # Sort by creation time, newest first
    files.sort(key=lambda x: x['created'], reverse=True)
    
    return jsonify({
        'success': True,
        'count': len(files),
        'screenshots': files
    }), 200


@app.route('/screenshots/<filename>', methods=['DELETE'])
def delete_screenshot(filename: str):
    """Delete a screenshot file."""
    # Security: prevent path traversal
    if '..' in filename or '/' in filename:
        return jsonify({
            'success': False,
            'error': 'Invalid filename'
        }), 400
    
    file_path = SCREENSHOTS_DIR / filename
    
    if not file_path.exists():
        return jsonify({
            'success': False,
            'error': 'File not found'
        }), 404
    
    try:
        file_path.unlink()
        return jsonify({
            'success': True,
            'message': f'Screenshot "{filename}" deleted'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Delete failed',
            'message': str(e)
        }), 500


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Handle HTTP exceptions."""
    return jsonify({
        'success': False,
        'error': e.name,
        'message': e.description
    }), e.code


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle unexpected exceptions."""
    return jsonify({
        'success': False,
        'error': 'Internal Server Error',
        'message': str(e)
    }), 500


if __name__ == '__main__':
    print(f"🚀 Playwright Screenshot API Server")
    print(f"================================")
    print(f"Port: {PORT}")
    print(f"Chrome: {CHROME_PATH}")
    print(f"Screenshots: {SCREENSHOTS_DIR}")
    print(f"================================")
    print(f"Endpoints:")
    print(f"  POST /screenshot     - Take a screenshot")
    print(f"  GET  /screenshots    - List all screenshots")
    print(f"  GET  /screenshots/<f> - Download a screenshot")
    print(f"  DELETE /screenshots/<f> - Delete a screenshot")
    print(f"  GET  /health         - Health check")
    print(f"================================")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
