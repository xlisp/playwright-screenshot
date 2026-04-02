#!/usr/bin/env python3
"""
Playwright Screenshot Tool (Offline Chrome Version)

Usage:
    python screenshot.py [URL] [OUTPUT_PATH] [OPTIONS]

Examples:
    python screenshot.py https://example.com screenshot.png
    python screenshot.py https://example.com screenshot.png --full-page
    python screenshot.py https://example.com screenshot.png --width 1920 --height 1080
"""

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


# Get Chrome path from environment variable or use default
CHROME_PATH = os.environ.get('CHROME_PATH', '/opt/chrome/chrome-linux64/chrome')

# Screenshot kill timeout in seconds. If a screenshot takes longer than this,
# the Chrome process is killed. Set via SCREENSHOT_KILL_TIMEOUT env var.
# Default 0 means disabled. Run `python benchmark.py` to find the right value
# for your pod's resource limits (CPU/memory).
SCREENSHOT_KILL_TIMEOUT = float(os.environ.get('SCREENSHOT_KILL_TIMEOUT', '0'))


def take_screenshot(
    url: str,
    output_path: str,
    width: int = 1920,
    height: int = 1080,
    full_page: bool = True,
    wait_time: int = 3000,
    timeout: int = 60000,
    kill_timeout: float = 0,
) -> bool:
    """
    Take a screenshot of a webpage.

    Args:
        url: The URL to screenshot
        output_path: Path to save the screenshot
        width: Viewport width in pixels
        height: Viewport height in pixels
        full_page: Whether to capture the full page or just the viewport
        wait_time: Time to wait after page load (ms)
        timeout: Navigation timeout (ms)
        kill_timeout: Max seconds for the entire operation. If exceeded,
                      Chrome is killed and False is returned. 0 = disabled.
                      Falls back to SCREENSHOT_KILL_TIMEOUT env var.

    Returns:
        True if successful, False otherwise
    """
    effective_kill_timeout = kill_timeout or SCREENSHOT_KILL_TIMEOUT

    browser = None

    def _kill_on_timeout(signum, frame):
        raise TimeoutError(
            f"Screenshot killed: exceeded {effective_kill_timeout:.1f}s limit"
        )

    try:
        # Set up SIGALRM-based kill timeout (Unix only)
        if effective_kill_timeout > 0 and hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, _kill_on_timeout)
            signal.alarm(int(effective_kill_timeout) + 1)

        t_start = time.time()

        with sync_playwright() as p:
            # Launch browser using local Chrome executable
            print(f"🔧 Using Chrome at: {CHROME_PATH}")
            browser = p.chromium.launch(
                headless=True,
                executable_path=CHROME_PATH
            )

            # Create a new page with specified viewport
            page = browser.new_page(viewport={'width': width, 'height': height})

            print(f"📸 Navigating to: {url}")
            page.goto(url, wait_until="networkidle", timeout=timeout)

            # Wait for dynamic content to load
            if wait_time > 0:
                print(f"⏳ Waiting {wait_time}ms for content to load...")
                page.wait_for_timeout(wait_time)

            # Ensure output directory exists
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Take screenshot
            page.screenshot(path=str(output_file), full_page=full_page)

            elapsed = time.time() - t_start
            print(f"✅ Screenshot saved to: {output_path} ({elapsed:.2f}s)")

            # Get file size
            file_size = output_file.stat().st_size
            print(f"📁 File size: {file_size / 1024:.2f} KB")

            # Close the browser
            browser.close()
            browser = None
            return True

    except TimeoutError as e:
        print(f"⏰ {e}", file=sys.stderr)
        # Force-kill Chrome process tree
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        return False

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        return False

    finally:
        # Always cancel the alarm
        if effective_kill_timeout > 0 and hasattr(signal, 'SIGALRM'):
            signal.alarm(0)


def main():
    parser = argparse.ArgumentParser(
        description="Take screenshots of web pages using Playwright",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com output.png
  %(prog)s https://github.com github.png --full-page
  %(prog)s https://example.com shot.png --width 1280 --height 720
        """
    )
    
    parser.add_argument(
        "url",
        help="URL of the webpage to screenshot"
    )
    parser.add_argument(
        "output",
        help="Output file path for the screenshot"
    )
    parser.add_argument(
        "--width", "-W",
        type=int,
        default=1920,
        help="Viewport width in pixels (default: 1920)"
    )
    parser.add_argument(
        "--height", "-H",
        type=int,
        default=1080,
        help="Viewport height in pixels (default: 1080)"
    )
    parser.add_argument(
        "--full-page", "-f",
        action="store_true",
        default=True,
        help="Capture full page screenshot (default: True)"
    )
    parser.add_argument(
        "--viewport-only", "-v",
        action="store_true",
        help="Capture only the viewport, not full page"
    )
    parser.add_argument(
        "--wait", "-w",
        type=int,
        default=3000,
        help="Wait time after page load in milliseconds (default: 3000)"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=60000,
        help="Navigation timeout in milliseconds (default: 60000)"
    )
    
    args = parser.parse_args()
    
    # Handle full_page vs viewport_only
    full_page = not args.viewport_only
    
    success = take_screenshot(
        url=args.url,
        output_path=args.output,
        width=args.width,
        height=args.height,
        full_page=full_page,
        wait_time=args.wait,
        timeout=args.timeout
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
