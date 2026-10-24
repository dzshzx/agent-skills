"""Exercise the release reuse shell against GitHub response fixtures."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

CASES = (
    "valid",
    "failed",
    "cancelled",
    "pending",
    "wrong-app",
    "wrong-sha",
    "wrong-workflow",
    "stale",
    "job-skipped",
    "job-failed",
    "run-query-fails",
    "jobs-query-fails",
)

# Fake `gh` that answers each API endpoint from the fixture file and fails the
# query that the case names.
FAKE_GH = textwrap.dedent("""\
    import json, os, sys
    data = json.load(open(os.environ["FIXTURE_RESPONSES"]))
    endpoint = sys.argv[-1]
    kind = "jobs" if "/jobs?" in endpoint else "checks" if "/check-runs?" in endpoint else "run"
    if data["case"] == kind + "-query-fails":
        sys.exit(1)
    print(json.dumps(data[kind]))
    """)


def reuse_script():
    """Return the reuse step's shell body from the CI workflow."""
    workflow = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
    text = workflow.read_text()
    return textwrap.dedent(
        text.split("        run: |\n", 1)[1].split("\n  validate:", 1)[0]
    )


def check_response(case):
    return {
        "name": "ci-ok",
        "app": {"id": 1 if case == "wrong-app" else 15368},
        "status": "in_progress" if case == "pending" else "completed",
        "conclusion": {"failed": "failure", "cancelled": "cancelled"}.get(
            case, "success"
        ),
        "details_url": "https://github.com/fixture/repo/actions/runs/10/job/20",
    }


def run_response(case):
    stamp = datetime.now(timezone.utc)
    if case == "stale":
        stamp -= timedelta(hours=73)
    return {
        "head_sha": "b" * 40 if case == "wrong-sha" else "a" * 40,
        "event": "pull_request",
        "path": ".github/workflows/other.yml"
        if case == "wrong-workflow"
        else ".github/workflows/ci.yml",
        "status": "completed",
        "conclusion": "success",
        "run_started_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_attempt": 1,
        "html_url": "https://github.com/fixture/repo/actions/runs/10",
    }


def job_response(case):
    return {
        "name": "validate",
        "status": "completed",
        "conclusion": {"job-skipped": "skipped", "job-failed": "failure"}.get(
            case, "success"
        ),
    }


def write_fixtures(root, case):
    """Write the GitHub responses and the fake `gh` for one case into root."""
    fixture = root / "responses.json"
    fixture.write_text(
        json.dumps(
            {
                "checks": [{"check_runs": [check_response(case)]}],
                "run": run_response(case),
                "jobs": [{"jobs": [job_response(case)]}],
                "case": case,
            }
        )
    )
    gh = root / "gh"
    gh.write_text(f"#!{sys.executable}\n" + FAKE_GH)
    gh.chmod(0o755)
    return fixture


def run_reuse(script, root, fixture):
    output = root / "output"
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "BASH_ENV": "/dev/null",
            "PATH": str(root) + os.pathsep + os.environ["PATH"],
            "FIXTURE_RESPONSES": str(fixture),
            "GITHUB_OUTPUT": str(output),
            "REPO": "fixture/repo",
            "SHA": "a" * 40,
            "RUN_ID": "99",
            "GH_TOKEN": "fixture",
        },
    )
    return result, output


class ReuseEvidenceTest(unittest.TestCase):
    def test_only_trusted_complete_exact_sha_runs_are_reused(self):
        script = reuse_script()
        for case in CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = write_fixtures(root, case)
                result, output = run_reuse(script, root, fixture)
                self.assertEqual(result.returncode, 0, result.stderr)
                values = dict(
                    line.split("=", 1) for line in output.read_text().splitlines()
                )
                self.assertEqual(
                    values["tested"],
                    "true" if case == "valid" else "false",
                    result.stdout + result.stderr,
                )
