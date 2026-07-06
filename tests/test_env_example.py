"""Tests for the .env.example template.

These are documentation/hygiene tests. They guard that `.env.example` ships only
a PLACEHOLDER webhook URL (never a real one) and warns the user not to commit
their real `.env`. (The webhook setup guidance now lives in the single README.md.)

The repo root is computed from this file's location so the tests do not depend
on the current working directory.
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_EXAMPLE = os.path.join(REPO_ROOT, ".env.example")

# A deliberately fake token string that must NEVER appear in the committed
# example file. If a real value ever gets pasted in, these tests are the
# tripwire.
FORBIDDEN_TOKEN = "FAKE_TOKEN_DO_NOT_USE"

PLACEHOLDER = "REPLACE_ME"
WEBHOOK_PREFIX = "discord.com/api/webhooks/"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# .env.example — existence + placeholder shape
# ---------------------------------------------------------------------------
def test_env_example_exists():
    assert os.path.isfile(ENV_EXAMPLE), ".env.example is missing at repo root"


def test_env_example_defines_webhook_variable():
    content = _read(ENV_EXAMPLE)
    assert "DISCORD_WEBHOOK_URL=" in content


def test_env_example_value_is_placeholder():
    content = _read(ENV_EXAMPLE)
    # The variable's value must be a placeholder, not a real token.
    match = re.search(r"^DISCORD_WEBHOOK_URL=(.*)$", content, flags=re.MULTILINE)
    assert match, "no DISCORD_WEBHOOK_URL=... line found"
    value = match.group(1).strip()
    assert PLACEHOLDER in value, "webhook value must contain the REPLACE_ME placeholder"


def test_env_example_warns_not_to_commit_dotenv():
    content = _read(ENV_EXAMPLE).lower()
    warns = ("never commit" in content) or ("not commit" in content)
    assert warns, "expected a 'never commit' / 'not commit' warning"
    assert ".env" in content, "the commit warning should mention .env"


# ---------------------------------------------------------------------------
# .env.example — no real / real-looking secret may leak in
# ---------------------------------------------------------------------------
def test_env_example_has_no_forbidden_test_token():
    content = _read(ENV_EXAMPLE)
    assert FORBIDDEN_TOKEN not in content


def test_env_example_every_webhook_line_is_placeholder():
    """Every line referencing the Discord webhook endpoint must be a placeholder.

    A robust, simple guard: any line containing ``discord.com/api/webhooks/``
    must also contain ``REPLACE_ME``. This rules out a real-looking id/token
    (long digit/hex runs) sneaking into the committed example.
    """
    for line in _read(ENV_EXAMPLE).splitlines():
        if WEBHOOK_PREFIX in line:
            assert PLACEHOLDER in line, (
                "webhook line without REPLACE_ME placeholder: %r" % line
            )


def test_env_example_no_reallooking_webhook_token():
    """Belt-and-suspenders: reject long pure digit/hex id/token segments.

    Parses each ``discord.com/api/webhooks/<id>/<token>`` occurrence and
    asserts the id and token segments are not long runs of digits/hex — the
    shape of a genuine Discord webhook URL.
    """
    content = _read(ENV_EXAMPLE)
    for m in re.finditer(r"discord\.com/api/webhooks/([^/\s]+)/([^/\s\"']+)", content):
        for segment in m.groups():
            assert PLACEHOLDER in segment or not re.fullmatch(
                r"[0-9a-fA-F]{12,}", segment
            ), "webhook URL segment looks like a real id/token: %r" % segment
