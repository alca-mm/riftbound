"""Guard tests for README.md — ensures the documented contract stays intact:
the three modes, the env var, the safety boundaries, the secret/GitHub notes,
and links to the dedicated docs. No secrets are ever asserted or embedded.
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


def test_readme_links_to_setup_and_upload_docs():
    text = _readme()
    assert "docs/DISCORD_WEBHOOK_SETUP.md" in text
    assert "docs/GITHUB_UPLOAD.md" in text


def test_readme_documents_optional_dotenv_loading():
    low = _readme().lower()
    assert ".env" in low
    assert "takes precedence" in low   # env var wins over .env


def test_setup_doc_documents_optional_dotenv_loading():
    with open(os.path.join(REPO_ROOT, "docs", "DISCORD_WEBHOOK_SETUP.md"), "r", encoding="utf-8") as fh:
        low = fh.read().lower()
    assert ".env" in low
    assert "takes precedence" in low


def test_readme_documents_best_clickable_link():
    low = _readme().lower()
    assert "clickable link" in low
    # notify-only: the user clicks manually, the bot buys nothing
    assert "click" in low
