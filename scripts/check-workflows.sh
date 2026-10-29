#!/bin/bash
# The GitHub workflows: actionlint, with shellcheck for their run: scripts, then zizmor.
# The same locally and in CI; actionlint comes from its image, which brings shellcheck.
set -euo pipefail
cd "$(dirname "$0")/.."

docker build -q -t enterich-actionlint .github/actionlint >/dev/null
# As the caller, so files only their owner may read are readable; the image runs as guest.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/repo:ro -w /repo enterich-actionlint -color
uv run zizmor --offline .github/workflows
