"""Safety guard tests for the Riftbound Watch scheduled workflow.

This workflow is the ONLY scheduled / manually-triggerable automation in the
repo. It is a NOTIFY-ONLY Discord watcher, so these checks lock down its safety
invariants with robust plain-text assertions (no third-party dependency
required):

* it may only obtain the Discord webhook from ``secrets.DISCORD_WEBHOOK_URL``
  and must never embed a hardcoded webhook URL;
* the schedule must be GENTLE -- at most hourly, never sub-hourly;
* it must run no git/gh mutation commands and no purchase automation;
* the safe manual default must be ``dry-run`` and it must declare
  least-privilege permissions.

If PyYAML happens to be importable we additionally parse the file to confirm it
is valid YAML, but we never require it (no new dependency is introduced).
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "riftbound-watch.yml"
)


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _cron_expressions(text):
    """Return every cron expression declared in the workflow text."""
    return re.findall(r'cron:\s*["\']?([^"\'\n]+)["\']?', text)


def test_workflow_file_exists():
    assert os.path.isfile(WORKFLOW_PATH), (
        "Expected Riftbound watch workflow at %s" % WORKFLOW_PATH
    )


def test_workflow_has_expected_triggers():
    text = _read(WORKFLOW_PATH)
    assert "workflow_dispatch" in text, (
        "Workflow should be manually triggerable via workflow_dispatch"
    )
    assert "schedule:" in text, "Workflow should run on a schedule"
    assert "cron:" in text, "Workflow schedule should declare a cron expression"


def test_schedule_is_gentle():
    text = _read(WORKFLOW_PATH)
    crons = _cron_expressions(text)
    assert crons, "Expected at least one cron expression in the workflow"
    for expr in crons:
        fields = expr.split()
        assert len(fields) == 5, (
            "cron expression %r should have five fields" % expr
        )
        minute = fields[0]
        # A fixed numeric minute means the job runs at most once per hour.
        assert minute.isdigit(), (
            "cron minute field %r must be a fixed number (not '*' or '*/n') "
            "so the schedule runs at most hourly" % minute
        )
    # Belt-and-suspenders: none of these aggressive patterns may appear.
    aggressive = [
        "* * * * *",
        "*/1 * * * *",
        "*/5",
        "*/10",
        "*/15",
        "*/20",
        "*/30",
    ]
    for pattern in aggressive:
        assert pattern not in text, (
            "aggressive/sub-hourly schedule pattern found: %r" % pattern
        )


def test_webhook_only_via_secret():
    text = _read(WORKFLOW_PATH)
    assert "secrets.DISCORD_WEBHOOK_URL" in text, (
        "Webhook must be provided via the DISCORD_WEBHOOK_URL secret"
    )
    assert "discord.com/api/webhooks/" not in text, (
        "Workflow must never contain a hardcoded Discord webhook URL"
    )


def test_no_git_or_gh_mutation_commands():
    text = _read(WORKFLOW_PATH)
    # actions/checkout@v4 is fine and expected -- we do not forbid "checkout".
    forbidden = [
        "git add",
        "git commit",
        "git push",
        "git remote",
        "git branch",
        "git rm",
        "gh workflow",
        "gh repo",
        "gh run",
    ]
    for command in forbidden:
        assert command not in text, (
            "Workflow must not run git/gh command: %r" % command
        )


def test_no_purchase_automation():
    lowered = _read(WORKFLOW_PATH).lower()
    for token in ("captcha", "add to cart", "purchase"):
        assert token not in lowered, (
            "Workflow must contain no purchase automation: %r" % token
        )


def test_safe_manual_default_is_dry_run():
    text = _read(WORKFLOW_PATH)
    assert "default: dry-run" in text, (
        "workflow_dispatch input should default to the safe 'dry-run' mode"
    )


def test_state_persistence_present():
    text = _read(WORKFLOW_PATH)
    assert "actions/cache" in text, (
        "Workflow should persist state via actions/cache"
    )
    assert "state.json" in text, "Workflow should cache the state.json file"


def test_runs_watcher_for_all_three_modes():
    text = _read(WORKFLOW_PATH)
    assert "watcher.py" in text, "Workflow should run the watcher"
    assert "--dry-run" in text, "Workflow should support the dry-run mode"
    assert "--test-webhook-random-riftbound" in text, (
        "Workflow should support the test-webhook mode"
    )
    assert "watch" in text, "Workflow should support the normal watch mode"


def test_least_privilege_permissions():
    text = _read(WORKFLOW_PATH)
    assert "contents: read" in text, (
        "Workflow should declare least-privilege permissions (contents: read)"
    )


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
