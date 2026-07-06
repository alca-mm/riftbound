"""Tests for the test-only CI workflow.

These checks guard the SAFETY invariants of the CI: it must never reference the
Discord webhook, never use repository secrets, never run on a schedule, and
never launch the watcher against real Riot pages. A robust plain-text check on
the workflow file is sufficient (and preferred) so this test has no third-party
dependencies. If PyYAML happens to be importable we additionally parse the file
to confirm it is valid YAML, but we never require it.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "tests.yml")
REQ_DEV_PATH = os.path.join(REPO_ROOT, "requirements-dev.txt")


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_workflow_file_exists():
    assert os.path.isfile(WORKFLOW_PATH), (
        "Expected CI workflow at %s" % WORKFLOW_PATH
    )


def test_workflow_runs_pytest_and_py_compile():
    text = _read(WORKFLOW_PATH)
    assert "pytest" in text, "Workflow should run pytest"
    assert "py_compile" in text, "Workflow should run py_compile"


def test_workflow_has_no_discord_webhook():
    text = _read(WORKFLOW_PATH)
    assert "DISCORD_WEBHOOK_URL" not in text, (
        "CI must never reference the Discord webhook"
    )


def test_workflow_has_no_secrets():
    text = _read(WORKFLOW_PATH).lower()
    assert "secrets." not in text, "CI must not use any repository secrets"


def test_workflow_has_no_schedule():
    text = _read(WORKFLOW_PATH)
    assert "schedule:" not in text, "CI must not run on a schedule/cron"


def test_workflow_does_not_run_watcher_directly():
    text = _read(WORKFLOW_PATH)
    # `py_compile watcher.py` is fine and expected; actually launching the
    # watcher (`python watcher.py`) is not.
    assert "python watcher.py" not in text, (
        "CI must never launch the watcher against real pages"
    )


def test_requirements_dev_exists_and_has_pytest():
    assert os.path.isfile(REQ_DEV_PATH), (
        "Expected requirements-dev.txt at %s" % REQ_DEV_PATH
    )
    text = _read(REQ_DEV_PATH)
    assert "pytest" in text, "requirements-dev.txt should install pytest"


def test_workflow_uses_least_privilege_permissions():
    text = _read(WORKFLOW_PATH)
    assert "contents: read" in text, (
        "CI should declare least-privilege permissions (contents: read)"
    )
    lowered = text.lower()
    assert "write-all" not in lowered, "CI must not grant write-all permissions"
    assert "permissions: write" not in lowered, (
        "CI must not grant broad write permissions"
    )


def test_workflow_triggers_are_push_and_pull_request_only():
    text = _read(WORKFLOW_PATH)
    assert "push:" in text, "CI should run on push"
    assert "pull_request:" in text, "CI should run on pull_request"
    # No other event triggers that could add an unsafe run context.
    for event in (
        "workflow_dispatch:",
        "workflow_run:",
        "repository_dispatch:",
        "schedule:",
    ):
        assert event not in text, "unexpected CI trigger: %s" % event


def test_workflow_is_valid_yaml_when_pyyaml_available():
    # Optional: only runs if PyYAML is installed. We never add it as a
    # dependency; the plain-text checks above are the real guarantees.
    try:
        import yaml
    except ImportError:
        return
    data = yaml.safe_load(_read(WORKFLOW_PATH))
    assert isinstance(data, dict), "Workflow should parse to a mapping"
    assert "jobs" in data, "Workflow should define at least one job"
