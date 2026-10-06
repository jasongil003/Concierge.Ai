import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_external_github_actions_are_pinned_to_full_commit_ids():
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows
    for workflow in workflows:
        source = workflow.read_text(encoding="utf-8")
        references = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", source, re.MULTILINE)
        for reference in references:
            if reference.startswith("./"):
                continue
            assert re.search(r"@[0-9a-f]{40}$", reference), f"Unpinned action in {workflow.name}: {reference}"


def test_external_container_images_use_verified_digest_syntax():
    checked_files = [
        ROOT / "Dockerfile",
        ROOT / "docker-compose.yml",
        *sorted((ROOT / ".github" / "workflows").glob("*.yml")),
    ]
    image_references: list[tuple[Path, str]] = []
    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            if line.lstrip().startswith("FROM "):
                image = line.split()[1]
                if not image.startswith("--"):
                    image_references.append((path, image))
            match = re.match(r"\s*image:\s*([^\s#]+)", line)
            if match:
                image_references.append((path, match.group(1)))
            for image in re.findall(r"\b(?:python|nginx|postgres|redis):[0-9][^\s\"']*", line):
                image_references.append((path, image))

    assert image_references
    for path, image in image_references:
        if image.startswith("concierge-ai:"):
            continue
        assert re.search(r"@sha256:[a-f0-9]{64}$", image), f"Unpinned image in {path.name}: {image}"


def test_release_workflow_fails_closed_on_signed_tag_requirements():
    source = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "RELEASE_TAG_PUBLIC_KEY" in source
    assert "RELEASE_TAG_SIGNER_FINGERPRINT" in source
    assert "Production release signing key is missing" in source
    assert "Approved release signer fingerprint is missing" in source
    assert "git verify-tag --raw \"$RELEASE_TAG\"" in source
    assert 'VALIDSIG ${RELEASE_TAG_SIGNER_FINGERPRINT}' in source
    assert 'test "$COMMIT" = "$(git rev-parse HEAD)"' in source
    assert 'SHA256="$(sha256sum "$ARTIFACT"' in source
    assert "printf 'SHA256=%s\\n' \"$SHA256\"" in source
    assert "WARNING: signed tag verification is not configured" not in source
    assert "If they are not configured" not in source


def test_psutil_is_an_exact_runtime_dependency_pin():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^psutil==[0-9]+\.[0-9]+\.[0-9]+$", requirements, re.MULTILINE)
