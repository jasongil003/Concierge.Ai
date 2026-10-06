import ast
import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIGEST = re.compile(r"@sha256:[a-f0-9]{64}$")
IMAGE_REFERENCE = re.compile(r"(?:[a-z0-9.-]+(?::[0-9]+)?/)*[a-z0-9][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*(?:@sha256:[a-f0-9]{64})?")
WORKFLOW_SUFFIXES = {".yml", ".yaml"}
LOCAL_PROJECT_IMAGES = {
    "concierge-ai:${CONCIERGE_VERSION:-local}",
    "concierge-ai:ci",
}


def _repository_files(root: Path) -> Iterator[Path]:
    ignored = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "playwright-report", "test-results"}
    for directory, child_directories, filenames in os.walk(root):
        child_directories[:] = sorted(name for name in child_directories if name not in ignored)
        for filename in filenames:
            yield Path(directory) / filename


def _dockerfiles(root: Path) -> list[Path]:
    return sorted(
        path for path in _repository_files(root)
        if path.name == "Dockerfile" or path.name.endswith(".Dockerfile")
    )


def _compose_files(root: Path) -> list[Path]:
    return sorted(
        path for path in _repository_files(root)
        if "compose" in path.name.lower() and path.suffix.lower() in WORKFLOW_SUFFIXES
    )


def _workflow_files(root: Path) -> list[Path]:
    workflow_root = root / ".github" / "workflows"
    if not workflow_root.exists():
        return []
    return sorted(
        path for path in workflow_root.rglob("*")
        if path.is_file() and path.suffix.lower() in WORKFLOW_SUFFIXES
    )


def _python_docker_run_references(root: Path) -> list[tuple[Path, str]]:
    references: list[tuple[Path, str]] = []
    for source_root in (root / "scripts", root / "tests", root / "loadtest"):
        if not source_root.exists():
            continue
        for path in sorted(source_root.rglob("*.py")):
            if any(part in {"__pycache__", ".venv", "test-results"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function_name = node.func.id if isinstance(node.func, ast.Name) else None
                argument_nodes: list[ast.AST] = []
                if function_name == "_docker" and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "run":
                    argument_nodes = node.args[1:]
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.args
                    and isinstance(node.args[0], ast.List)
                ):
                    command = node.args[0].elts
                    if len(command) >= 2 and all(isinstance(item, ast.Constant) for item in command[:2]):
                        if [command[0].value, command[1].value] == ["docker", "run"]:
                            argument_nodes = command[2:]
                for argument in argument_nodes:
                    for value in ast.walk(argument):
                        if isinstance(value, ast.Constant) and isinstance(value.value, str) and IMAGE_REFERENCE.fullmatch(value.value):
                            references.append((path, value.value))
    return references


def _dockerfile_image(line: str) -> str | None:
    parts = line.strip().split()
    if not parts or parts[0].upper() != "FROM":
        return None
    image_index = 1
    while image_index < len(parts) and parts[image_index].startswith("--"):
        image_index += 1
    if image_index >= len(parts):
        return None
    return parts[image_index].split("#", maxsplit=1)[0]


def _external_image_references(root: Path) -> list[tuple[Path, str]]:
    references: list[tuple[Path, str]] = []
    references.extend(_python_docker_run_references(root))
    dockerfiles = set(_dockerfiles(root))
    scanned_files = [*dockerfiles, *_compose_files(root), *_workflow_files(root)]
    for path in sorted(set(scanned_files)):
        for line in path.read_text(encoding="utf-8").splitlines():
            image = _dockerfile_image(line) if path in dockerfiles else None
            if image:
                references.append((path, image))
            match = re.match(r"\s*image:\s*([^\s#]+)", line)
            if match:
                references.append((path, match.group(1).strip("\"'")))
    return references


def _is_local_project_image(image: str) -> bool:
    return image in LOCAL_PROJECT_IMAGES


def _assert_external_images_are_pinned(image_references: list[tuple[Path, str]]) -> None:
    assert image_references, "No container image references were found."
    for path, image in image_references:
        if _is_local_project_image(image) or image == "scratch":
            continue
        assert IMAGE_DIGEST.search(image), f"Unpinned image in {path}: {image}"


def test_external_github_actions_are_pinned_to_full_commit_ids():
    workflows = _workflow_files(ROOT)
    assert workflows
    for workflow in workflows:
        source = workflow.read_text(encoding="utf-8")
        references = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", source, re.MULTILINE)
        for reference in references:
            if reference.startswith("./"):
                continue
            assert re.search(r"@[0-9a-f]{40}$", reference), f"Unpinned action in {workflow.name}: {reference}"


def test_external_container_images_use_verified_digest_syntax():
    references = _external_image_references(ROOT)
    _assert_external_images_are_pinned(references)


def test_image_scanner_recursively_detects_root_and_loadtest_dockerfiles():
    paths = {path.relative_to(ROOT).as_posix() for path in _dockerfiles(ROOT)}

    assert "Dockerfile" in paths
    assert "loadtest/mock-ai.Dockerfile" in paths
    images_by_path = {path.relative_to(ROOT).as_posix(): image for path, image in _external_image_references(ROOT)}
    assert images_by_path["Dockerfile"].startswith("python:")
    assert images_by_path["loadtest/mock-ai.Dockerfile"].startswith("python:")


def test_python_smoke_helpers_pin_external_docker_run_images():
    references = _python_docker_run_references(ROOT)
    images = [image for _, image in references]

    assert any(image.startswith("postgres:16@sha256:") for image in images)
    assert any(image.startswith("redis:7-alpine@sha256:") for image in images)
    _assert_external_images_are_pinned(references)


def test_image_scanner_detects_compose_images(tmp_path: Path):
    compose = tmp_path / "deployment" / "docker-compose.poc.yaml"
    compose.parent.mkdir()
    compose.write_text(
        "services:\n  database:\n    image: postgres:16@sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )

    references = _external_image_references(tmp_path)

    assert (compose, "postgres:16@sha256:" + "a" * 64) in references


def test_external_image_requires_full_lowercase_sha256_digest():
    with pytest.raises(AssertionError, match="Unpinned image"):
        _assert_external_images_are_pinned([(Path("loadtest/mock-ai.Dockerfile"), "python:3.12-slim")])

    _assert_external_images_are_pinned(
        [(Path("loadtest/mock-ai.Dockerfile"), "python:3.12-slim@sha256:" + "b" * 64)]
    )


def test_local_project_built_image_is_not_an_external_dependency():
    _assert_external_images_are_pinned([(Path("docker-compose.yml"), "concierge-ai:${CONCIERGE_VERSION:-local}")])
    _assert_external_images_are_pinned([(Path(".github/workflows/ci.yml"), "concierge-ai:ci")])


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
