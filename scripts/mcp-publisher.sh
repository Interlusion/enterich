#!/bin/bash
# The MCP Registry's publisher for the release workflow (ITEM-003, releasing guide).
#   scripts/mcp-publisher.sh DIR   download the pinned version to DIR/mcp-publisher
# The archive must be signed by the registry's own release workflow at that tag; cosign
# checks it before anything is unpacked. Dependabot can't see the pin.
set -euo pipefail
version=v1.8.7
dir=$1
os=$(uname -s | tr '[:upper:]' '[:lower:]')
arch=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
archive="mcp-publisher_${os}_${arch}.tar.gz"
base="https://github.com/modelcontextprotocol/registry/releases/download/$version"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl --fail --location --silent --show-error --output "$work/$archive" "$base/$archive"
curl --fail --location --silent --show-error --output "$work/$archive.sigstore.json" \
  "$base/$archive.sigstore.json"
cosign verify-blob \
  --bundle "$work/$archive.sigstore.json" \
  --certificate-identity "https://github.com/modelcontextprotocol/registry/.github/workflows/release.yml@refs/tags/$version" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$work/$archive"
tar -xzf "$work/$archive" -C "$dir" mcp-publisher
