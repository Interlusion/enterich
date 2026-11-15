"""What the workflows promise: gitleaks over every pushed commit ("Secrets never in Git",
AGENTS.md; ADR-005-toolchain-and-dependencies.md)."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
ZEROS = "0" * 40


def job(name: str) -> str:
    """The lines of one job of ci.yml, up to the next job."""
    text = CI.read_text()
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.M | re.S)
    assert match is not None, f"ci.yml has no job {name!r}"
    return match.group(1)


def range_for(base: str) -> str:
    """The log range the secrets job's script computes for the base commit `base`."""
    script = job("secrets").split("run: |\n", 1)[1]
    head = script[: script.index("\n          fi\n") + len("\n          fi\n")]
    result = subprocess.run(  # noqa: S603 - the repository's own script, no input
        ["bash", "-c", f'{head}\nprintf %s "$range"'],  # noqa: S607 - bash from PATH, as CI
        env={"BASE": base, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_the_secrets_job_runs_the_pinned_gitleaks_redacted_over_the_full_history() -> None:
    secrets = job("secrets")
    assert "fetch-depth: 0" in secrets
    assert "docker build -q -t gitleaks .github/gitleaks" in secrets
    assert 'git --redact --no-banner --log-opts="$range" .' in secrets
    assert "BASE: ${{ github.event.pull_request.base.sha || github.event.before }}" in secrets


@pytest.mark.parametrize(
    ("base", "expected"),
    [("abc123", "abc123..HEAD"), ("", "HEAD"), (ZEROS, "HEAD")],
)
def test_the_secrets_job_scans_every_commit_since_the_base(base: str, expected: str) -> None:
    assert range_for(base) == expected


def test_git_ignores_env_files() -> None:
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in ignored
    assert ".env.*" in ignored
