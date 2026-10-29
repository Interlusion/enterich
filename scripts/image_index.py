"""The dry run's check of the release image: an OCI image layout written by buildx.

    python3 scripts/image_index.py LAYOUT OUT NAME PLATFORM...

It checks that the layout holds one image named NAME (image:tag) for exactly the given
platforms (os/arch), each with an SBOM and a provenance attestation without GitHub's
event payload (which names people and their email addresses), and writes those
in-toto statements to OUT as <os>_<arch>-sbom.spdx.json and <os>_<arch>-provenance.json.
Standard library only: the release workflow runs it with the runner's Python (3.12).
"""

import json
import sys
from pathlib import Path
from typing import Any

INDEX = "application/vnd.oci.image.index.v1+json"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"
FILES = ("sbom.spdx.json", "provenance.json")


class LayoutError(Exception):
    pass


def _blob(layout: Path, digest: str) -> Any:
    algorithm, _, value = digest.partition(":")
    return json.loads((layout / "blobs" / algorithm / value).read_text())


def _file(predicate: str) -> str | None:
    """The file an attestation goes to: the SPDX SBOM, or SLSA provenance (v0.2 or v1)."""
    if predicate == "https://spdx.dev/Document":
        return "sbom.spdx.json"
    return "provenance.json" if predicate.startswith("https://slsa.dev/provenance/") else None


def check(layout: Path, name: str, platforms: list[str]) -> dict[str, Any]:
    """The attestation statements by output file name; LayoutError when the layout isn't
    the image asked for."""
    top = json.loads((layout / "index.json").read_text())["manifests"]
    named = [m for m in top if m.get("annotations", {}).get("io.containerd.image.name") == name]
    if len(top) != 1 or len(named) != 1 or named[0]["mediaType"] != INDEX:
        raise LayoutError(f"the layout doesn't hold exactly one image index named {name}")
    entries = _blob(layout, named[0]["digest"])["manifests"]
    images = {
        f"{e['platform']['os']}/{e['platform']['architecture']}": e["digest"]
        for e in entries
        if e["mediaType"] == MANIFEST and e.get("platform", {}).get("os") != "unknown"
    }
    if sorted(images) != sorted(platforms):
        raise LayoutError(f"platforms {sorted(images)}, not {sorted(platforms)}")
    attestations = {
        e["annotations"]["vnd.docker.reference.digest"]: e["digest"]
        for e in entries
        if e.get("annotations", {}).get("vnd.docker.reference.type") == "attestation-manifest"
    }
    statements: dict[str, Any] = {}
    for platform, digest in sorted(images.items()):
        if digest not in attestations:
            raise LayoutError(f"{platform} has no attestations")
        found: dict[str, Any] = {}
        for layer in _blob(layout, attestations[digest])["layers"]:
            file = _file(layer.get("annotations", {}).get("in-toto.io/predicate-type", ""))
            if file is not None:
                found.setdefault(file, _blob(layout, layer["digest"]))
        missing = [file for file in FILES if file not in found]
        if missing:
            raise LayoutError(f"{platform} lacks {', '.join(missing)}")
        build = found["provenance.json"].get("predicate", {}).get("buildDefinition", {})
        if "github_event_payload" in build.get("internalParameters", {}):
            raise LayoutError(f"{platform}'s provenance carries GitHub's event payload")
        prefix = platform.replace("/", "_")
        statements |= {f"{prefix}-{file}": statement for file, statement in found.items()}
    return statements


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("usage: image_index.py LAYOUT OUT NAME PLATFORM...", file=sys.stderr)
        return 2
    layout, out, name, platforms = Path(argv[0]), Path(argv[1]), argv[2], argv[3:]
    try:
        statements = check(layout, name, platforms)
    except LayoutError as exc:
        print(f"The image isn't as a release needs it: {exc}.", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    for file, statement in statements.items():
        (out / file).write_text(json.dumps(statement, indent=2) + "\n")
    print(f"{name}: {', '.join(sorted(platforms))}, each with SBOM and provenance")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
