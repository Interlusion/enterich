"""The dry run's check of the release image (scripts/image_index.py, used by image.yml)."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "image_index.py"
NAME = "ghcr.io/interlusion/enterich:0.1.0"
PLATFORMS = ["linux/amd64", "linux/arm64"]
SBOM = "https://spdx.dev/Document"
PROVENANCE = "https://slsa.dev/provenance/v1"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("image_index", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


image_index = load()


def blob(layout: Path, content: Any) -> str:
    data = json.dumps(content).encode()
    digest = hashlib.sha256(data).hexdigest()
    (layout / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
    (layout / "blobs" / "sha256" / digest).write_bytes(data)
    return f"sha256:{digest}"


def statement(predicate: str, platform: str, internal: dict[str, Any]) -> dict[str, Any]:
    body = {"buildDefinition": {"internalParameters": internal}} if predicate == PROVENANCE else {}
    return {"predicateType": predicate, "platform": platform, "predicate": body}


def write_layout(
    layout: Path,
    name: str = NAME,
    platforms: list[str] = PLATFORMS,
    predicates: tuple[str, ...] = (SBOM, PROVENANCE),
    internal: dict[str, Any] | None = None,
) -> None:
    """An OCI image layout as buildx writes it: a named index of the platforms' manifests,
    each with an attestation manifest of in-toto statements; `internal` goes into the
    provenance's internal parameters."""
    entries: list[dict[str, Any]] = []
    for platform in platforms:
        os, arch = platform.split("/")
        image = blob(layout, {"layers": []})
        layers = [
            {
                "mediaType": "application/vnd.in-toto+json",
                "digest": blob(layout, statement(p, platform, internal or {})),
                "annotations": {"in-toto.io/predicate-type": p},
            }
            for p in predicates
        ]
        entries += [
            {
                "mediaType": image_index.MANIFEST,
                "digest": image,
                "platform": {"architecture": arch, "os": os},
            },
            {
                "mediaType": image_index.MANIFEST,
                "digest": blob(layout, {"layers": layers}),
                "platform": {"architecture": "unknown", "os": "unknown"},
                "annotations": {
                    "vnd.docker.reference.digest": image,
                    "vnd.docker.reference.type": "attestation-manifest",
                },
            },
        ]
    index = blob(layout, {"manifests": entries})
    top = {
        "manifests": [
            {
                "mediaType": image_index.INDEX,
                "digest": index,
                "annotations": {"io.containerd.image.name": name},
            }
        ]
    }
    (layout / "index.json").write_text(json.dumps(top))


def test_a_release_image_gives_its_attestations_per_platform(tmp_path: Path) -> None:
    write_layout(tmp_path)
    statements = image_index.check(tmp_path, NAME, PLATFORMS)
    assert sorted(statements) == [
        "linux_amd64-provenance.json",
        "linux_amd64-sbom.spdx.json",
        "linux_arm64-provenance.json",
        "linux_arm64-sbom.spdx.json",
    ]
    assert statements["linux_arm64-sbom.spdx.json"] == {
        "predicateType": SBOM,
        "platform": "linux/arm64",
        "predicate": {},
    }


def test_slsa_provenance_v02_counts_too(tmp_path: Path) -> None:
    write_layout(tmp_path, predicates=(SBOM, "https://slsa.dev/provenance/v0.2"))
    assert len(image_index.check(tmp_path, NAME, PLATFORMS)) == 4


@pytest.mark.parametrize(
    ("layout", "says"),
    [
        (
            {"name": "ghcr.io/interlusion/enterich:0.2.0"},
            "named ghcr.io/interlusion/enterich:0.1.0",
        ),
        ({"platforms": ["linux/arm64"]}, "platforms ['linux/arm64']"),
        ({"platforms": [*PLATFORMS, "linux/s390x"]}, "not ['linux/amd64', 'linux/arm64']"),
        ({"predicates": (PROVENANCE,)}, "linux/amd64 lacks sbom.spdx.json"),
        ({"predicates": (SBOM,)}, "linux/amd64 lacks provenance.json"),
        ({"predicates": ()}, "lacks sbom.spdx.json, provenance.json"),
    ],
)
def test_an_image_unlike_a_release_is_refused(
    tmp_path: Path, layout: dict[str, Any], says: str
) -> None:
    write_layout(tmp_path, **layout)
    with pytest.raises(image_index.LayoutError) as info:
        image_index.check(tmp_path, NAME, PLATFORMS)
    assert says in str(info.value)


def test_provenance_with_githubs_event_payload_is_refused(tmp_path: Path) -> None:
    # A tag push's payload names the pusher and the commit's authors with their emails.
    payload = {"pusher": {"name": "someone", "email": "someone@example.com"}}
    write_layout(tmp_path, internal={"github_event_payload": payload})
    with pytest.raises(image_index.LayoutError, match="carries GitHub's event payload"):
        image_index.check(tmp_path, NAME, PLATFORMS)


def test_provenance_with_other_github_parameters_passes(tmp_path: Path) -> None:
    write_layout(tmp_path, internal={"github_repository": "interlusion/enterich"})
    assert len(image_index.check(tmp_path, NAME, PLATFORMS)) == 4


def test_a_platform_without_attestations_is_refused(tmp_path: Path) -> None:
    write_layout(tmp_path)
    top = json.loads((tmp_path / "index.json").read_text())
    index = image_index._blob(tmp_path, top["manifests"][0]["digest"])
    images = [e for e in index["manifests"] if "annotations" not in e]
    top["manifests"][0]["digest"] = blob(tmp_path, {"manifests": images})
    (tmp_path / "index.json").write_text(json.dumps(top))
    with pytest.raises(image_index.LayoutError, match="linux/amd64 has no attestations"):
        image_index.check(tmp_path, NAME, PLATFORMS)


def test_main_writes_the_statements(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_layout(tmp_path / "oci")
    out = tmp_path / "out"
    assert image_index.main([str(tmp_path / "oci"), str(out), NAME, *PLATFORMS]) == 0
    assert len(list(out.iterdir())) == 4
    statement = json.loads((out / "linux_amd64-provenance.json").read_text())
    assert statement["predicateType"] == PROVENANCE
    assert "each with SBOM and provenance" in capsys.readouterr().out


def test_main_refuses_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_layout(tmp_path / "oci", platforms=["linux/arm64"])
    out = tmp_path / "out"
    assert image_index.main([str(tmp_path / "oci"), str(out), NAME, *PLATFORMS]) == 1
    assert not out.exists()
    assert "isn't as a release needs it" in capsys.readouterr().err


def test_too_few_arguments_are_refused() -> None:
    assert image_index.main(["layout", "out", NAME]) == 2
