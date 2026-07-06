"""Tests for config.py — loading the Discord webhook URL from env / .env.

These tests are written test-first (TDD). They exercise the public contract of
``config`` and guard two safety invariants along the way:

  * resolving the webhook URL must NEVER mutate ``os.environ`` and must NEVER
    create a file (the module reads config, it does not write it);
  * only ``DISCORD_WEBHOOK_URL`` is ever consulted — no other ``.env`` key is
    exported anywhere.

All values used here are obviously-fake placeholders. A real
``discord.com/api/webhooks/<id>/<token>`` value must never appear in this repo.
"""
import os

import config


# Obviously-fake test values — never a real webhook URL/token.
ENV_VALUE = "https://hooks.example.test/env-value"
DOTENV_VALUE = "https://hooks.example.test/dotenv-value"
NORMAL_FAKE = "https://hooks.example.test/local-fake-abc"


# ---------------------------------------------------------------------------
# module constants
# ---------------------------------------------------------------------------
def test_module_constants():
    assert config.WEBHOOK_ENV_VAR == "DISCORD_WEBHOOK_URL"
    assert config.DEFAULT_ENV_PATH == ".env"
    assert "REPLACE_ME" in config.PLACEHOLDER_MARKERS
    assert "FAKE_TOKEN_DO_NOT_USE" in config.PLACEHOLDER_MARKERS


# ---------------------------------------------------------------------------
# parse_env_file
# ---------------------------------------------------------------------------
def test_parse_env_file_basic_key_value():
    result = config.parse_env_file("DISCORD_WEBHOOK_URL=" + NORMAL_FAKE)
    assert result == {"DISCORD_WEBHOOK_URL": NORMAL_FAKE}


def test_parse_env_file_ignores_blank_and_comment_lines():
    text = "\n".join(
        [
            "",
            "   ",
            "# this is a comment",
            "   # indented comment",
            "KEY=value",
            "",
        ]
    )
    assert config.parse_env_file(text) == {"KEY": "value"}


def test_parse_env_file_strips_surrounding_double_quotes():
    assert config.parse_env_file('KEY="quoted value"') == {"KEY": "quoted value"}


def test_parse_env_file_strips_surrounding_single_quotes():
    assert config.parse_env_file("KEY='quoted value'") == {"KEY": "quoted value"}


def test_parse_env_file_strips_only_one_matching_quote_pair():
    # A mismatched pair is left untouched; only ONE matching pair is stripped.
    assert config.parse_env_file("KEY=\"only_left") == {"KEY": '"only_left'}
    assert config.parse_env_file("KEY='outer\"inner\"outer'") == {
        "KEY": 'outer"inner"outer'
    }


def test_parse_env_file_splits_on_first_equals():
    # A value containing '=' must survive intact.
    assert config.parse_env_file("KEY=a=b=c") == {"KEY": "a=b=c"}


def test_parse_env_file_strips_whitespace_around_key_and_value():
    assert config.parse_env_file("  KEY   =   value  ") == {"KEY": "value"}


def test_parse_env_file_ignores_lines_without_equals():
    assert config.parse_env_file("this line has no equals") == {}


def test_parse_env_file_multiple_keys():
    text = "A=1\nB=2\nDISCORD_WEBHOOK_URL=" + NORMAL_FAKE
    assert config.parse_env_file(text) == {
        "A": "1",
        "B": "2",
        "DISCORD_WEBHOOK_URL": NORMAL_FAKE,
    }


def test_parse_env_file_never_raises_on_empty():
    assert config.parse_env_file("") == {}


# ---------------------------------------------------------------------------
# load_env_file
# ---------------------------------------------------------------------------
def test_load_env_file_missing_path_returns_empty(tmp_path):
    missing = tmp_path / "does-not-exist.env"
    assert not missing.exists()
    assert config.load_env_file(str(missing)) == {}


def test_load_env_file_reads_and_parses(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nDISCORD_WEBHOOK_URL=" + DOTENV_VALUE + "\nOTHER=x\n",
        encoding="utf-8",
    )
    assert config.load_env_file(str(env_file)) == {
        "DISCORD_WEBHOOK_URL": DOTENV_VALUE,
        "OTHER": "x",
    }


# ---------------------------------------------------------------------------
# is_placeholder_webhook
# ---------------------------------------------------------------------------
def test_is_placeholder_webhook_none():
    assert config.is_placeholder_webhook(None) is True


def test_is_placeholder_webhook_empty():
    assert config.is_placeholder_webhook("") is True


def test_is_placeholder_webhook_whitespace():
    assert config.is_placeholder_webhook("   ") is True


def test_is_placeholder_webhook_replace_me_marker():
    value = "https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME"
    assert config.is_placeholder_webhook(value) is True


def test_is_placeholder_webhook_fake_token_marker():
    value = "https://hooks.example.test/FAKE_TOKEN_DO_NOT_USE"
    assert config.is_placeholder_webhook(value) is True


def test_is_placeholder_webhook_marker_is_case_insensitive():
    assert config.is_placeholder_webhook("x/replace_me/y") is True


def test_is_placeholder_webhook_normal_fake_is_not_placeholder():
    assert config.is_placeholder_webhook(NORMAL_FAKE) is False


# ---------------------------------------------------------------------------
# resolve_webhook_url
# ---------------------------------------------------------------------------
def test_resolve_env_priority_wins_over_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_WEBHOOK_URL=" + DOTENV_VALUE + "\n", encoding="utf-8")
    result = config.resolve_webhook_url(
        environ={"DISCORD_WEBHOOK_URL": ENV_VALUE}, env_path=str(env_file)
    )
    assert result == ENV_VALUE


def test_resolve_dotenv_fallback_when_env_absent(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_WEBHOOK_URL=" + DOTENV_VALUE + "\n", encoding="utf-8")
    result = config.resolve_webhook_url(environ={}, env_path=str(env_file))
    assert result == DOTENV_VALUE


def test_resolve_empty_env_value_treated_as_unset(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_WEBHOOK_URL=" + DOTENV_VALUE + "\n", encoding="utf-8")
    result = config.resolve_webhook_url(
        environ={"DISCORD_WEBHOOK_URL": ""}, env_path=str(env_file)
    )
    assert result == DOTENV_VALUE


def test_resolve_neither_env_nor_dotenv_returns_none(tmp_path):
    missing = tmp_path / "does-not-exist.env"
    assert config.resolve_webhook_url(environ={}, env_path=str(missing)) is None


def test_resolve_only_loads_webhook_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=x\n", encoding="utf-8")
    assert config.resolve_webhook_url(environ={}, env_path=str(env_file)) is None


def test_resolve_does_not_mutate_environ_or_create_file(tmp_path):
    missing = tmp_path / "does-not-exist.env"
    fake_environ = {"UNRELATED": "keep"}
    before = dict(fake_environ)
    os_environ_before = dict(os.environ)

    result = config.resolve_webhook_url(environ=fake_environ, env_path=str(missing))

    assert result is None
    # environ passed in is untouched...
    assert fake_environ == before
    # ...os.environ is untouched...
    assert dict(os.environ) == os_environ_before
    # ...and no file was created at the missing path.
    assert not missing.exists()


def test_resolve_defaults_environ_to_os_environ(monkeypatch, tmp_path):
    # With DISCORD_WEBHOOK_URL set in the real environment and no .env, the
    # default (environ=None -> os.environ) must be consulted.
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", ENV_VALUE)
    missing = tmp_path / "does-not-exist.env"
    assert config.resolve_webhook_url(env_path=str(missing)) == ENV_VALUE
