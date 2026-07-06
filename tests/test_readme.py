"""Guard tests for README.md — the single Markdown doc for the project.

Ensures the documented contract stays intact: the three modes, the env var, the
safety boundaries, the secret/GitHub notes, GitHub Actions operation, and that
README.md is the ONLY Markdown file in the project. No secrets are embedded.
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _readme():
    with open(os.path.join(REPO_ROOT, "README.md"), "r", encoding="utf-8") as fh:
        return fh.read()


def test_readme_exists_and_nonempty():
    text = _readme()
    assert text.strip()


def test_readme_mentions_env_var_and_modes():
    text = _readme()
    assert "DISCORD_WEBHOOK_URL" in text
    assert "python watcher.py" in text
    assert "--dry-run" in text
    assert "--test-webhook-random-riftbound" in text


def test_readme_documents_baseline_and_no_state_side_effects():
    low = _readme().lower()
    assert "baseline" in low
    # dry-run and test-webhook must be described as not changing state
    assert "dry" in low and "state" in low


def test_readme_states_safety_boundaries():
    low = _readme().lower()
    # notify-only: no auto-buy / login / checkout / captcha / aggressive scraping
    assert "buy" in low
    assert "log in" in low or "login" in low
    assert "checkout" in low
    assert "captcha" in low
    assert "aggress" in low  # "aggressive scraping" / "scrape aggressively"


def test_readme_has_secret_and_git_safety_notes():
    low = _readme().lower()
    assert ".env" in low
    assert "state.json" in low
    # never commit / never share the secret
    assert "never commit" in low or "not commit" in low


def test_readme_documents_optional_dotenv_loading():
    low = _readme().lower()
    assert ".env" in low
    assert "takes precedence" in low   # env var wins over .env


def test_readme_documents_best_clickable_link():
    low = _readme().lower()
    assert "clickable link" in low
    # notify-only: the user clicks manually, the bot buys nothing
    assert "click" in low


def test_readme_documents_github_actions_operation():
    text = _readme()
    low = text.lower()
    assert "riftbound-watch.yml" in text
    assert "run workflow" in low
    assert "watch" in low
    # webhook comes from a GitHub repository Secret; state via cache
    assert "repository secret" in low
    assert "cache" in low
    # manual gh one-liner and the primary merch target page
    assert "gh workflow run riftbound-watch.yml" in text
    assert "merch.riotgames.com/de-de/category/riftbound" in text


def test_readme_marks_git_as_manual_only():
    low = _readme().lower()
    assert "only run these yourself" in low   # git/gh commands are manual-only


def test_readme_documents_github_secret_and_placeholder():
    low = _readme().lower()
    assert "secrets and variables" in low or "new repository secret" in low
    assert "replace_me" in low   # unedited placeholder is not sent


def test_only_readme_markdown_file_in_project():
    skip_dirs = {".venv", "venv", "env", ".git", ".idea", "__pycache__", ".pytest_cache"}
    md_files = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            if name.lower().endswith(".md"):
                rel = os.path.relpath(os.path.join(root, name), REPO_ROOT)
                md_files.append(rel.replace(os.sep, "/"))
    assert md_files == ["README.md"], (
        "Only README.md may be a Markdown file; found: %r" % sorted(md_files)
    )
