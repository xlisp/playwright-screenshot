"""Tests for github_page_generator.py — HTML generation helpers."""

import pytest

from github_page_generator import format_date, format_number, language_color, generate_html


# ═══════════════════════════════════════════════════════════════════════
#  format_date
# ═══════════════════════════════════════════════════════════════════════

class TestFormatDate:
    def test_iso_utc(self):
        assert format_date("2024-01-15T12:30:00Z") == "Jan 15, 2024"

    def test_iso_with_offset(self):
        result = format_date("2024-06-01T00:00:00+08:00")
        assert "Jun" in result
        assert "2024" in result

    def test_none(self):
        assert format_date(None) == "N/A"

    def test_empty(self):
        assert format_date("") == "N/A"

    def test_invalid_string(self):
        result = format_date("not-a-date")
        # Should return the raw string as fallback
        assert result == "not-a-date"


# ═══════════════════════════════════════════════════════════════════════
#  format_number
# ═══════════════════════════════════════════════════════════════════════

class TestFormatNumber:
    def test_small(self):
        assert format_number(42) == "42"

    def test_zero(self):
        assert format_number(0) == "0"

    def test_thousand(self):
        assert format_number(1500) == "1.5K"

    def test_exact_thousand(self):
        assert format_number(1000) == "1.0K"

    def test_million(self):
        assert format_number(2500000) == "2.5M"

    def test_exact_million(self):
        assert format_number(1000000) == "1.0M"

    def test_just_below_thousand(self):
        assert format_number(999) == "999"


# ═══════════════════════════════════════════════════════════════════════
#  language_color
# ═══════════════════════════════════════════════════════════════════════

class TestLanguageColor:
    def test_python(self):
        assert language_color("Python") == "#3572A5"

    def test_javascript(self):
        assert language_color("JavaScript") == "#f1e05a"

    def test_go(self):
        assert language_color("Go") == "#00ADD8"

    def test_unknown_language(self):
        assert language_color("Brainfuck") == "#8b8b8b"

    def test_none(self):
        assert language_color(None) == "#8b8b8b"


# ═══════════════════════════════════════════════════════════════════════
#  generate_html
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateHtml:
    def test_basic_structure(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "<!DOCTYPE html>" in html
        assert "octocat" in html
        assert "The Octocat" in html

    def test_contains_bio(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "GitHub mascot" in html

    def test_contains_repos(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "Hello-World" in html
        assert "Spoon-Knife" in html

    def test_contains_events(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "Push" in html

    def test_contains_stats(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "10.0K" in html  # followers: 10000
        assert "Followers" in html

    def test_language_bar(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "lang-segment" in html
        assert "Python" in html
        assert "JavaScript" in html

    def test_fork_badge(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "Fork" in html  # Spoon-Knife is a fork

    def test_topics(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "hello" in html
        assert "world" in html

    def test_empty_repos(self, sample_profile, sample_events):
        html = generate_html(sample_profile, [], sample_events)
        assert "<!DOCTYPE html>" in html

    def test_empty_events(self, sample_profile, sample_repos):
        html = generate_html(sample_profile, sample_repos, [])
        assert "No recent public events" in html

    def test_missing_profile_fields(self):
        minimal_profile = {"login": "bare", "public_repos": 0, "followers": 0, "following": 0, "public_gists": 0}
        html = generate_html(minimal_profile, [], [])
        assert "bare" in html

    def test_long_description_truncated(self, sample_profile, sample_events):
        repos = [{
            "name": "long-desc",
            "full_name": "user/long-desc",
            "description": "x" * 200,
            "html_url": "#",
            "language": "Python",
            "stargazers_count": 1,
            "forks_count": 0,
            "open_issues_count": 0,
            "watchers_count": 1,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "topics": [],
            "fork": False,
            "archived": False,
            "homepage": None,
            "size": 0,
            "default_branch": "main",
        }]
        html = generate_html(sample_profile, repos, sample_events)
        assert "..." in html

    def test_company_and_location(self, sample_profile, sample_repos, sample_events):
        html = generate_html(sample_profile, sample_repos, sample_events)
        assert "@github" in html
        assert "San Francisco" in html
