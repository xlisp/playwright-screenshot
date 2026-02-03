#!/usr/bin/env python3
"""
Playwright Screenshot Tool (Firefox Version)

Usage:
    python screenshot.py [URL] [OUTPUT_PATH] [OPTIONS]

Examples:
    python screenshot.py https://example.com screenshot.png
    python screenshot.py https://example.com screenshot.png --full-page
    python screenshot.py https://example.com screenshot.png --width 1920 --height 1080
"""

import argparse
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright


def take_screenshot(
    url: str,
    output_path: str,
    width: int = 1920,
    height: int = 1080,
    full_page: bool = True,
    wait_time: int = 3000,
    timeout: int = 60000
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
    
    Returns:
        True if successful, False otherwise
    """
    try:
        with sync_playwright() as p:
            # Launch Firefox browser
            print("🔧 Using Firefox browser")
            browser = p.firefox.launch(
                headless=True
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
            print(f"✅ Screenshot saved to: {output_path}")
            
            # Get file size
            file_size = output_file.stat().st_size
            print(f"📁 File size: {file_size / 1024:.2f} KB")
            
            # Close the browser
            browser.close()
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return False


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
