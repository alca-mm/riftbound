"""config.py — resolve the Discord webhook URL for the riot watcher.

The watcher needs exactly one secret: the Discord webhook URL. This module
loads it from the environment, with an optional fallback to a local ``.env``
file, following an ENVIRONMENT-WINS priority.

SECURITY: the webhook URL is a secret. This module must NEVER log, raise, or
otherwise expose any secret value. It only ever handles the ENV VAR NAME in
messages. It also never mutates the environment and never creates files — it
reads configuration, it does not write it.

Stdlib only. There is no ``python-dotenv`` dependency; the tiny ``.env`` parser
here is intentionally minimal (``KEY=VALUE`` lines).
"""
import logging
import os

logger = logging.getLogger("riot.config")

# The single environment variable that carries the Discord webhook URL.
WEBHOOK_ENV_VAR = "DISCORD_WEBHOOK_URL"

# Default location of the optional local ``.env`` fallback file.
DEFAULT_ENV_PATH = ".env"

# Substrings that mark a value as a non-usable placeholder rather than a real
# webhook URL. Matched case-insensitively.
PLACEHOLDER_MARKERS = ("REPLACE_ME", "FAKE_TOKEN_DO_NOT_USE")


def parse_env_file(text: str) -> dict:
    """Parse simple ``KEY=VALUE`` lines from ``text`` into a dict.

    Rules:
      * Blank lines, and lines whose first non-whitespace char is ``#``, are
        ignored.
      * Lines without ``=`` are ignored.
      * The line is split on the FIRST ``=`` only, so a value containing ``=``
        survives intact.
      * Whitespace around the key and the value is stripped.
      * ONE matching pair of surrounding single OR double quotes is stripped
        from the value.

    Never raises.
    """
    result = {}
    if not text:
        return result

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        value = _strip_one_quote_pair(value)
        result[key] = value
    return result


def _strip_one_quote_pair(value: str) -> str:
    """Strip ONE matching pair of surrounding single or double quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env_file(path: str = DEFAULT_ENV_PATH) -> dict:
    """Return the parsed contents of the ``.env`` file at ``path``.

    If ``path`` does not exist or cannot be read, return ``{}``. Never raises,
    and never logs the file contents or any parsed value.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        # Missing / unreadable file is a normal condition — the fallback is
        # simply absent. Do not log the path's contents or any value.
        return {}
    return parse_env_file(text)


def is_placeholder_webhook(value) -> bool:
    """Return ``True`` when ``value`` is NOT a real, usable webhook URL.

    That is: ``None``, empty, or whitespace-only, OR containing any
    :data:`PLACEHOLDER_MARKERS` entry (case-insensitive). Otherwise ``False``.
    """
    if value is None:
        return True
    text = str(value)
    if not text.strip():
        return True
    lowered = text.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker.lower() in lowered:
            return True
    return False


def resolve_webhook_url(*, environ=None, env_path: str = DEFAULT_ENV_PATH):
    """Resolve the Discord webhook URL with ENVIRONMENT priority.

    Resolution order:
      1. ``environ`` (defaults to :data:`os.environ`). If it holds a NON-EMPTY
         ``DISCORD_WEBHOOK_URL``, return it — the environment wins even when a
         ``.env`` file specifies a different value.
      2. Otherwise, if ``env_path`` exists, return its ``DISCORD_WEBHOOK_URL``
         value (via :func:`load_env_file`), or ``None`` if that key is absent.
      3. Otherwise, return ``None``.

    Returns a ``str`` or ``None``. Consults ONLY ``DISCORD_WEBHOOK_URL`` — no
    other ``.env`` key is exported anywhere. Never mutates ``environ`` /
    ``os.environ``, never creates a file, and never logs the value.
    """
    if environ is None:
        environ = os.environ

    # 1. Environment wins when it carries a non-empty value.
    env_value = environ.get(WEBHOOK_ENV_VAR)
    if env_value:
        logger.debug("Resolved %s from environment.", WEBHOOK_ENV_VAR)
        return env_value

    # 2. Fall back to the .env file, consulting only the webhook key.
    dotenv = load_env_file(env_path)
    dotenv_value = dotenv.get(WEBHOOK_ENV_VAR)
    if dotenv_value is not None:
        logger.debug("Resolved %s from env file.", WEBHOOK_ENV_VAR)
        return dotenv_value

    # 3. Nothing configured.
    logger.debug("%s is not configured.", WEBHOOK_ENV_VAR)
    return None
