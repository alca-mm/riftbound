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


def test_readme_documents_primary_merch_target():
    text = _readme()
    # Primary watch focus is the Riot merch Riftbound category (shop items).
    assert "merch.riotgames.com/de-de/category/riftbound" in text


def test_readme_documents_markdown_local_policy():
    low = _readme().lower()
    # Extra Markdown docs may exist locally but are git-ignored; README is tracked.
    assert "git-ignored" in low
    assert "readme" in low


def test_readme_documents_github_actions_interval():
    low = _readme().lower()
    # GitHub Actions runs on an interval (now every 2 hours), not continuously.
    assert "interval" in low
    assert "continuous" in low          # "does not continuously ..."
    assert "2 hours" in low             # scheduled watch cadence


def test_readme_documents_test_webhook_availability_preference():
    low = _readme().lower()
    assert "pre-order" in low
    assert "available" in low
    assert "availability is not confirmed" in low   # honest unknown fallback


def test_readme_documents_embedded_product_discovery():
    low = _readme().lower()
    assert "embedded product data" in low
    assert "/de-de/product/" in low   # the product URL pattern is documented


def test_readme_documents_status_report_mode():
    text = _readme()
    low = text.lower()
    assert "--status-report" in text
    assert "status report" in low
    assert "no links" in low
    # status-report is now MANUAL only — no longer tied to the automatic schedule
    assert "manual" in low
    assert "every 30 minutes" not in low   # old scheduled cadence must be gone
    assert "30 minutes" not in low         # the 30-minute cadence is removed


def test_readme_documents_auto_posts_only_new_hits():
    low = _readme().lower()
    # Automatic/scheduled run posts ONLY on new relevant hits ...
    assert "only new relevant hits" in low
    assert "only" in low and "new" in low
    # ... and sends nothing when there is nothing new.
    assert "nothing new" in low
    assert "no discord message" in low


def test_readme_documents_no_status_spam():
    low = _readme().lower()
    # The automatic schedule does not send "nothing new" status spam.
    assert "no status spam" in low


def test_readme_documents_status_report_is_manual():
    text = _readme()
    low = text.lower()
    assert "status report" in low
    assert "manual" in low
    # the manual dispatch path is documented
    assert "run workflow" in low
    assert "--status-report" in text


def test_readme_documents_test_webhook_is_manual():
    low = _readme().lower()
    assert "test-webhook" in low
    assert "manual" in low


def test_readme_documents_scheduled_watch_baseline():
    low = _readme().lower()
    # First scheduled/watch run writes a baseline and sends no message;
    # later runs post new hits with a clickable link.
    assert "baseline" in low
    assert "clickable link" in low
