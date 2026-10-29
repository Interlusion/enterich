"""The release notes: a version's section of CHANGELOG.md (Keep a Changelog).

    python3 scripts/changelog.py X.Y.Z            # the `## [X.Y.Z]` section, or exit 1
    python3 scripts/changelog.py X.Y.Z --draft    # falls back to `## [Unreleased]`

Standard library only: the release workflow runs it with the runner's Python (3.12).
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"


def section(changelog: str, name: str) -> str | None:
    """The body of the `## [name]` section, up to the next `## ` heading or the link
    definitions at the end; None when there is no such section or it is empty. A
    release's heading carries its date, and `[YANKED]` if it was withdrawn."""
    heading = re.compile(rf"^## \[{re.escape(name)}\]( - \d{{4}}-\d{{2}}-\d{{2}}( \[YANKED\])?)?$")
    body: list[str] | None = None
    for line in changelog.splitlines():
        if body is None:
            if heading.match(line):
                body = []
        elif line.startswith("## ") or re.match(r"^\[[^\]]+\]: ", line):
            break
        else:
            body.append(line)
    text = "\n".join(body or []).strip()
    return text or None


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2) or (len(argv) == 2 and argv[1] != "--draft"):
        print("usage: changelog.py X.Y.Z [--draft]", file=sys.stderr)
        return 2
    version, draft = argv[0], len(argv) == 2
    text = CHANGELOG.read_text()
    notes = section(text, version)
    if notes is None and draft:
        notes = section(text, "Unreleased")
        if notes is not None:
            print(f"No section for {version}; the draft uses Unreleased.", file=sys.stderr)
    if notes is None:
        print(f"CHANGELOG.md has no section `## [{version}]`.", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
