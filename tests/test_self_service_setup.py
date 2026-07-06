"""Guard test for docs/SELF_SERVICE_SETUP.md — the standalone GitHub-upload +
Discord-setup walkthrough. Ensures the safety-critical guidance stays present and
that no real webhook token leaks into the guide. No secrets are embedded here.
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_PATH = os.path.join(REPO_ROOT, "docs", "SELF_SERVICE_SETUP.md")
README_PATH = os.path.join(REPO_ROOT, "README.md")

# Built by concatenation so this test file never matches its own secret scan.
WEBHOOK_PREFIX = "discord.com/api/" + "webhooks/"


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def test_self_service_doc_exists_and_nonempty():
    assert os.path.isfile(DOC_PATH), "Expected docs/SELF_SERVICE_SETUP.md"
    assert _read(DOC_PATH).strip()


def test_doc_mentions_webhook_env_var_and_env_rules():
    low = _read(DOC_PATH).lower()
    assert "discord_webhook_url" in low
    assert "never commit" in low and ".env" in low
    assert "takes precedence" in low          # shell env var wins over .env
    assert "replace_me" in low                 # placeholder must be replaced


def test_doc_mentions_state_json_not_uploaded():
    low = _read(DOC_PATH).lower()
    assert "state.json" in low
    assert "upload" in low                     # must never be uploaded


def test_doc_documents_all_three_modes_and_baseline():
    low = _read(DOC_PATH).lower()
    assert "--dry-run" in low
    assert "--test-webhook-random-riftbound" in low
    assert "baseline" in low                    # first run = baseline, no message


def test_doc_mentions_clickable_link():
    assert "clickable link" in _read(DOC_PATH).lower()


def test_doc_marks_git_as_manual_only():
    low = _read(DOC_PATH).lower()
    assert "only run these yourself" in low     # git commands are manual-only


def test_doc_states_safety_boundaries():
    low = _read(DOC_PATH).lower()
    assert "notify-only" in low
    assert "auto-buy" in low
    assert "login" in low
    assert "checkout" in low
    assert "captcha" in low
    assert "aggressive scraping" in low


def test_doc_states_ci_never_posts_to_discord():
    low = _read(DOC_PATH).lower()
    assert "github actions are test-only" in low
    assert "never post to discord" in low


def test_doc_has_no_real_webhook_token():
    text = _read(DOC_PATH)
    for line in text.splitlines():
        if WEBHOOK_PREFIX in line:
            # Every webhook reference must be an obvious placeholder/template.
            assert (
                "REPLACE_ME" in line or "<id>" in line or "<token>" in line
            ), "Possible real webhook token in SELF_SERVICE_SETUP.md"


def test_readme_links_to_self_service_doc():
    assert "docs/SELF_SERVICE_SETUP.md" in _read(README_PATH)
