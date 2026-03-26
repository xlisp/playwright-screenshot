#!/usr/bin/env python3
"""
GitHub Profile HTML Page Generator

Fetches GitHub user data via API and generates a beautiful HTML profile page,
then takes a screenshot of it using Playwright.

Usage:
    python github_page_generator.py <username> [--screenshot] [--output-dir ./output]

Examples:
    python github_page_generator.py octocat
    python github_page_generator.py octocat --screenshot
    python github_page_generator.py octocat --screenshot --output-dir /tmp/output
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

from github_api import GitHubAPI


def format_date(iso_str: str | None) -> str:
    """Format ISO date string to human readable."""
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y")
    except Exception:
        return iso_str


def format_number(n: int) -> str:
    """Format number with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def language_color(lang: str | None) -> str:
    """Return a color for a programming language."""
    colors = {
        "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#2b7489",
        "Java": "#b07219", "Go": "#00ADD8", "Rust": "#dea584",
        "C++": "#f34b7d", "C": "#555555", "C#": "#178600",
        "Ruby": "#701516", "PHP": "#4F5D95", "Swift": "#F05138",
        "Kotlin": "#A97BFF", "Dart": "#00B4AB", "Shell": "#89e051",
        "HTML": "#e34c26", "CSS": "#563d7c", "Vue": "#41b883",
        "Jupyter Notebook": "#DA5B0B", "Lua": "#000080",
        "Haskell": "#5e5086", "Scala": "#c22d40", "R": "#198CE7",
        "Clojure": "#db5855", "Elixir": "#6e4a7e",
    }
    return colors.get(lang, "#8b8b8b")


def generate_html(profile: dict, repos: list[dict], events: list[dict]) -> str:
    """Generate a complete HTML page for a GitHub user profile."""

    username = profile.get("login", "unknown")
    name = profile.get("name") or username
    avatar = profile.get("avatar_url", "")
    bio = profile.get("bio") or ""
    company = profile.get("company") or ""
    location = profile.get("location") or ""
    blog = profile.get("blog") or ""
    created = format_date(profile.get("created_at"))

    # ── Repo cards ────────────────────────────────────────────────────
    repo_cards = ""
    top_repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:12]
    for r in top_repos:
        lang = r.get("language") or ""
        lang_html = (
            f'<span class="lang-dot" style="background:{language_color(lang)}"></span>'
            f'<span>{lang}</span>'
        ) if lang else ""
        topics_html = "".join(
            f'<span class="topic">{t}</span>' for t in (r.get("topics") or [])[:3]
        )
        desc = r.get("description") or "No description"
        if len(desc) > 120:
            desc = desc[:117] + "..."
        repo_cards += f"""
        <div class="repo-card">
            <div class="repo-header">
                <svg class="repo-icon" viewBox="0 0 16 16" width="16" height="16">
                    <path fill-rule="evenodd" d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" fill="currentColor"/>
                </svg>
                <a href="{r.get('html_url', '#')}" class="repo-name">{r['name']}</a>
                {' <span class="fork-badge">Fork</span>' if r.get('fork') else ''}
            </div>
            <p class="repo-desc">{desc}</p>
            <div class="repo-topics">{topics_html}</div>
            <div class="repo-meta">
                <span class="repo-lang">{lang_html}</span>
                <span class="repo-stat">⭐ {format_number(r.get('stargazers_count', 0))}</span>
                <span class="repo-stat">🍴 {format_number(r.get('forks_count', 0))}</span>
                <span class="repo-updated">Updated {format_date(r.get('pushed_at'))}</span>
            </div>
        </div>"""

    # ── Language stats ────────────────────────────────────────────────
    lang_counts: dict[str, int] = {}
    for r in repos:
        l = r.get("language")
        if l:
            lang_counts[l] = lang_counts.get(l, 0) + 1
    top_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    total_lang = sum(c for _, c in top_langs) or 1
    lang_bar = ""
    lang_legend = ""
    for lang, count in top_langs:
        pct = count / total_lang * 100
        lang_bar += f'<div class="lang-segment" style="width:{pct:.1f}%;background:{language_color(lang)}" title="{lang} {pct:.1f}%"></div>'
        lang_legend += f'<span class="lang-item"><span class="lang-dot" style="background:{language_color(lang)}"></span>{lang} <small>{pct:.0f}%</small></span>'

    # ── Events timeline ───────────────────────────────────────────────
    event_items = ""
    event_icons = {
        "PushEvent": "📤", "CreateEvent": "🆕", "WatchEvent": "⭐",
        "ForkEvent": "🍴", "IssuesEvent": "🐛", "PullRequestEvent": "🔀",
        "IssueCommentEvent": "💬", "DeleteEvent": "🗑️",
        "ReleaseEvent": "🚀", "PublicEvent": "🌐",
    }
    for evt in events[:8]:
        icon = event_icons.get(evt.get("type", ""), "📌")
        etype = evt.get("type", "").replace("Event", "")
        event_items += f"""
        <div class="event-item">
            <span class="event-icon">{icon}</span>
            <span class="event-type">{etype}</span>
            <span class="event-repo">{evt.get('repo', '')}</span>
            <span class="event-date">{format_date(evt.get('created_at'))}</span>
        </div>"""

    # ── Full HTML ─────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} (@{username}) - GitHub Profile</title>
<style>
:root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --orange: #d29922; --red: #f85149;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.5; }}
a {{ color:var(--accent); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}

.container {{ max-width:1200px; margin:0 auto; padding:32px 24px; }}
.header {{ display:flex; gap:32px; align-items:flex-start; margin-bottom:32px; padding-bottom:32px; border-bottom:1px solid var(--border); }}
.avatar {{ width:200px; height:200px; border-radius:50%; border:3px solid var(--border); flex-shrink:0; }}
.profile-info {{ flex:1; }}
.profile-info h1 {{ font-size:28px; font-weight:600; }}
.profile-info h1 span {{ font-weight:300; color:var(--text2); }}
.bio {{ color:var(--text2); margin:8px 0 16px; font-size:16px; }}
.meta-row {{ display:flex; flex-wrap:wrap; gap:16px; color:var(--text2); font-size:14px; margin-bottom:12px; }}
.meta-row svg {{ width:16px; height:16px; fill:var(--text2); vertical-align:-3px; margin-right:4px; }}
.stats {{ display:flex; gap:24px; margin-top:16px; }}
.stat {{ text-align:center; padding:12px 20px; background:var(--surface); border:1px solid var(--border); border-radius:8px; min-width:100px; }}
.stat-value {{ font-size:24px; font-weight:700; color:var(--accent); }}
.stat-label {{ font-size:12px; color:var(--text2); text-transform:uppercase; letter-spacing:.5px; }}

.section {{ margin-bottom:32px; }}
.section-title {{ font-size:20px; font-weight:600; margin-bottom:16px; display:flex; align-items:center; gap:8px; }}

.lang-bar {{ display:flex; height:10px; border-radius:5px; overflow:hidden; margin-bottom:12px; }}
.lang-segment {{ transition:width .3s; }}
.lang-legend {{ display:flex; flex-wrap:wrap; gap:12px; font-size:13px; color:var(--text2); }}
.lang-item {{ display:flex; align-items:center; gap:4px; }}
.lang-dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}

.repo-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:16px; }}
.repo-card {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:20px; display:flex; flex-direction:column; transition:border-color .2s; }}
.repo-card:hover {{ border-color:var(--accent); }}
.repo-header {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
.repo-icon {{ color:var(--text2); flex-shrink:0; }}
.repo-name {{ font-size:16px; font-weight:600; color:var(--accent); }}
.fork-badge {{ font-size:11px; background:var(--border); color:var(--text2); padding:1px 8px; border-radius:12px; }}
.repo-desc {{ color:var(--text2); font-size:13px; flex:1; margin-bottom:12px; }}
.repo-topics {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }}
.topic {{ font-size:11px; background:rgba(88,166,255,.15); color:var(--accent); padding:2px 10px; border-radius:12px; }}
.repo-meta {{ display:flex; flex-wrap:wrap; gap:12px; font-size:12px; color:var(--text2); align-items:center; }}
.repo-lang {{ display:flex; align-items:center; gap:4px; }}
.repo-stat {{ display:flex; align-items:center; gap:2px; }}
.repo-updated {{ margin-left:auto; }}

.events {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; overflow:hidden; }}
.event-item {{ display:flex; align-items:center; gap:12px; padding:12px 16px; border-bottom:1px solid var(--border); font-size:14px; }}
.event-item:last-child {{ border-bottom:none; }}
.event-icon {{ font-size:18px; }}
.event-type {{ font-weight:600; min-width:110px; }}
.event-repo {{ color:var(--accent); flex:1; }}
.event-date {{ color:var(--text2); font-size:12px; }}

.footer {{ text-align:center; color:var(--text2); font-size:12px; margin-top:40px; padding-top:24px; border-top:1px solid var(--border); }}
.gen-badge {{ display:inline-block; background:var(--surface); border:1px solid var(--border); padding:4px 12px; border-radius:6px; margin-top:8px; }}
</style>
</head>
<body>
<div class="container">
    <!-- Profile Header -->
    <div class="header">
        <img class="avatar" src="{avatar}" alt="{username}" />
        <div class="profile-info">
            <h1>{name} <span>@{username}</span></h1>
            <p class="bio">{bio}</p>
            <div class="meta-row">
                {'<span>🏢 ' + company + '</span>' if company else ''}
                {'<span>📍 ' + location + '</span>' if location else ''}
                {'<span>🔗 <a href="' + blog + '">' + blog + '</a></span>' if blog else ''}
                <span>📅 Joined {created}</span>
            </div>
            <div class="stats">
                <div class="stat"><div class="stat-value">{format_number(profile.get('public_repos', 0))}</div><div class="stat-label">Repos</div></div>
                <div class="stat"><div class="stat-value">{format_number(profile.get('followers', 0))}</div><div class="stat-label">Followers</div></div>
                <div class="stat"><div class="stat-value">{format_number(profile.get('following', 0))}</div><div class="stat-label">Following</div></div>
                <div class="stat"><div class="stat-value">{format_number(profile.get('public_gists', 0))}</div><div class="stat-label">Gists</div></div>
            </div>
        </div>
    </div>

    <!-- Language Stats -->
    <div class="section">
        <h2 class="section-title">📊 Languages</h2>
        <div class="lang-bar">{lang_bar}</div>
        <div class="lang-legend">{lang_legend}</div>
    </div>

    <!-- Repositories -->
    <div class="section">
        <h2 class="section-title">📦 Top Repositories</h2>
        <div class="repo-grid">{repo_cards}</div>
    </div>

    <!-- Recent Activity -->
    <div class="section">
        <h2 class="section-title">⚡ Recent Activity</h2>
        <div class="events">{event_items if event_items else '<div class="event-item"><span>No recent public events</span></div>'}</div>
    </div>

    <div class="footer">
        <p>Generated by <strong>playwright-screenshot</strong> GitHub Profile Viewer</p>
        <div class="gen-badge">🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
    </div>
</div>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(
        description="Generate GitHub profile HTML page and optional screenshot"
    )
    parser.add_argument("username", help="GitHub username")
    parser.add_argument(
        "--output-dir", "-o", default="./output",
        help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--screenshot", "-s", action="store_true",
        help="Also take a screenshot of the generated page"
    )
    parser.add_argument("--token", help="GitHub token (overrides Vault)")
    parser.add_argument(
        "--repos", type=int, default=30,
        help="Number of repos to fetch (default: 30)"
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Fetch GitHub data ─────────────────────────────────────────────
    print(f"\n🔍 Fetching GitHub data for: {args.username}")
    api = GitHubAPI(token=args.token)

    try:
        profile = api.get_user_profile(args.username)
        repos = api.get_user_repos(args.username, per_page=args.repos)
        events = api.get_user_events(args.username)
    except Exception as e:
        print(f"❌ GitHub API error: {e}")
        sys.exit(1)

    # ── Save raw JSON ─────────────────────────────────────────────────
    json_path = output_dir / f"{args.username}_data.json"
    with open(json_path, "w") as f:
        json.dump({"profile": profile, "repos": repos, "events": events}, f, indent=2)
    print(f"📄 JSON data saved: {json_path}")

    # ── Generate HTML ─────────────────────────────────────────────────
    html = generate_html(profile, repos, events)
    html_path = output_dir / f"{args.username}_profile.html"
    with open(html_path, "w") as f:
        f.write(html)
    print(f"🌐 HTML page saved: {html_path}")

    # ── Screenshot ────────────────────────────────────────────────────
    if args.screenshot:
        from screenshot import take_screenshot

        png_path = output_dir / f"{args.username}_profile.png"
        file_url = f"file://{html_path.resolve()}"
        print(f"\n📸 Taking screenshot of generated page...")
        success = take_screenshot(
            url=file_url,
            output_path=str(png_path),
            width=1280,
            height=900,
            full_page=True,
            wait_time=1000,
            timeout=30000,
        )
        if success:
            print(f"✅ Screenshot saved: {png_path}")
        else:
            print("❌ Screenshot failed")
            sys.exit(1)

    print(f"\n✨ Done! Files in: {output_dir}/")


if __name__ == "__main__":
    main()
