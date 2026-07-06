"""Repo-hygiene tests — guard the repository before it is published to GitHub.

These tests never touch the network and never read a real secret. They assert
that the ignore rules and every tracked text file are safe to publish for this
notify-only Discord watcher.

Repo root is derived from this file's location so the tests work regardless of
the current working directory.
"""
import fnmatch
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The webhook host + path prefix we scan for. It is assembled by concatenation
# so that this very test file never contains the contiguous literal substring
# it is searching for (otherwise the scan would flag itself).
WEBHOOK_NEEDLE = "discord.com/api/" + "webhooks/"

# Markers that prove a webhook-shaped value is a deliberate, safe placeholder
# rather than a leaked real token. "…" is the elided unicode ellipsis "…".
PLACEHOLDER_MARKERS = ("REPLACE_ME", "FAKE_TOKEN_DO_NOT_USE", "…")

# Only these text-ish files are inspected by the secret scan.
SCAN_EXTENSIONS = (
    ".py", ".md", ".json", ".txt", ".yml", ".yaml", ".example", ".cfg", ".ini",
)
SCAN_FILENAMES = (".gitignore", ".env.example")

# Directories that are never part of the published, tracked source.
SKIP_DIRS = {
    ".git", ".venv", "venv", "env", ".idea", "__pycache__", ".pytest_cache",
}

# A run this long of id/token characters is the shape of a genuine Discord
# webhook id or token — the thing we must never commit without a placeholder.
_REAL_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{12,}")
# Characters that terminate the value that follows the webhook prefix.
_TAIL_DELIMS = set(" \t\"'`<>\\)")


def _webhook_line_has_real_value(line):
    """True if a webhook prefix on this line is followed by a real-looking value.

    A bare prefix constant (``discord.com/api/webhooks/``), an angle-bracket
    template (``<id>/<token>``) or an elided ``…`` value has no real-looking
    id/token and is inherently safe; a long id/token run is the danger sign.
    """
    start = 0
    while True:
        idx = line.find(WEBHOOK_NEEDLE, start)
        if idx == -1:
            return False
        tail = line[idx + len(WEBHOOK_NEEDLE):]
        cut = len(tail)
        for i, ch in enumerate(tail):
            if ch in _TAIL_DELIMS:
                cut = i
                break
        if _REAL_TOKEN_RE.search(tail[:cut]):
            return True
        start = idx + 1


def _read(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def _iter_scan_files():
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        # Prune skipped directories in place so os.walk does not descend them.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SCAN_FILENAMES or name.endswith(SCAN_EXTENSIONS):
                yield os.path.join(dirpath, name)


# ---------------------------------------------------------------------------
# .gitignore
# ---------------------------------------------------------------------------
def test_gitignore_exists():
    assert os.path.isfile(os.path.join(REPO_ROOT, ".gitignore"))


def test_gitignore_excludes_essentials():
    content = _read(os.path.join(REPO_ROOT, ".gitignore"))
    for entry in (
        ".env",
        "state.json",
        "__pycache__/",
        ".pytest_cache/",
        ".venv/",
        "venv/",
        "env/",
    ):
        assert entry in content, f".gitignore must exclude {entry!r}"


# ---------------------------------------------------------------------------
# Documentation publish policy — only the root README.md is tracked; every
# other Markdown doc is kept locally but git-ignored.
# ---------------------------------------------------------------------------
def _md_path_is_ignored(relpath):
    """Emulate the two Markdown .gitignore rules for a repo-relative path.

    Rule 1 ``*.md``   — ignore every Markdown file (matched on its basename, so
                        it applies at any directory depth).
    Rule 2 ``!/README.md`` — re-include (un-ignore) the root ``README.md`` only.

    Dependency-free (fnmatch + os.path); no gitwildmatch/pathspec needed.
    """
    norm = relpath.replace(os.sep, "/")
    ignored = fnmatch.fnmatch(os.path.basename(norm), "*.md")
    if norm == "README.md":  # leading-slash anchor re-includes the root README
        ignored = False
    return ignored


def test_gitignore_ignores_extra_markdown_but_keeps_root_readme():
    lines = [
        line.strip()
        for line in _read(os.path.join(REPO_ROOT, ".gitignore")).splitlines()
    ]
    assert "*.md" in lines, ".gitignore must ignore all Markdown via '*.md'"
    assert any(
        neg in lines for neg in ("!/README.md", "!README.md")
    ), ".gitignore must re-include the root README via '!/README.md'"


def test_markdown_policy_sanity_check():
    # Root README stays tracked; extra docs anywhere are ignored.
    assert not _md_path_is_ignored("README.md")
    assert _md_path_is_ignored("docs/changes/foo.md")
    assert _md_path_is_ignored("GUIDE.md")
    assert _md_path_is_ignored(os.path.join("docs", "notes.md"))
    # Non-Markdown files are unaffected by this policy.
    assert not _md_path_is_ignored("main.py")


# ---------------------------------------------------------------------------
# REPO HYGIENE — no real secret must ever be committed.
# ---------------------------------------------------------------------------
def test_no_real_webhook_value_committed():
    offenders = []
    for path in _iter_scan_files():
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            if _webhook_line_has_real_value(line) and not any(
                marker in line for marker in PLACEHOLDER_MARKERS
            ):
                offenders.append((os.path.relpath(path, REPO_ROOT), lineno))
    assert not offenders, (
        "Possible real Discord webhook value committed (a webhook URL with a "
        "real-looking id/token must instead be a placeholder containing one of "
        f"{PLACEHOLDER_MARKERS}): {offenders}"
    )
