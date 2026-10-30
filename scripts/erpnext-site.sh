#!/bin/bash
# The ERPNext site for the end-to-end tests (tests/e2e/compose.yml, ITEM-004).
#   scripts/erpnext-site.sh up     start it, or keep the one running; prints the URL
#   scripts/erpnext-site.sh down   remove it with its data
# Then: E2E_ERPNEXT_URL=http://127.0.0.1:8080 uv run pytest tests/e2e
# The tests seed the site themselves, once; a site kept running is reused.
set -euo pipefail
cd "$(dirname "$0")/.."

compose=(docker compose -f tests/e2e/compose.yml)
case "${1:-}" in
  up)
    if ! "${compose[@]}" up --detach --wait; then
      "${compose[@]}" logs --no-log-prefix --tail 5 site >&2
      exit 1
    fi
    echo "E2E_ERPNEXT_URL=http://127.0.0.1:8080"
    ;;
  down)
    "${compose[@]}" down --volumes
    ;;
  *)
    echo "usage: $0 up|down" >&2
    exit 2
    ;;
esac
