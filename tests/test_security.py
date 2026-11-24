import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path):
    return yaml.load(
        (ROOT / path).read_text(),
        Loader=yaml.BaseLoader,
    )


def test_postgres_scram_authentication():
    compose = load_yaml("compose.yaml")
    args = compose["services"]["db"]["environment"][
        "POSTGRES_INITDB_ARGS"
    ]

    assert "--auth-local=scram-sha-256" in args
    assert "--auth-host=scram-sha-256" in args


def test_postgres_data_checksums():
    compose = load_yaml("compose.yaml")
    args = compose["services"]["db"]["environment"][
        "POSTGRES_INITDB_ARGS"
    ]

    assert "--data-checksums" in args


def test_postgres_authenticated_healthcheck():
    compose = load_yaml("compose.yaml")
    healthcheck = compose["services"]["db"]["healthcheck"]["test"]
    command = " ".join(healthcheck)

    assert "PGPASSWORD=" in command
    assert "$$POSTGRES_PASSWORD" in command
    assert "psql" in command
    assert "127.0.0.1" in command
    assert "SELECT 1" in command
    assert "ON_ERROR_STOP=1" in command


def test_postgres_password_required():
    compose = load_yaml("compose.yaml")
    password = compose["services"]["db"]["environment"][
        "POSTGRES_PASSWORD"
    ]

    assert password.startswith("${POSTGRES_PASSWORD:?")


def test_container_images_digest_pinned():
    dockerfile = (ROOT / "Dockerfile").read_text()
    compose = load_yaml("compose.yaml")

    assert re.search(
        r"^FROM python:[^\s]+@sha256:[0-9a-f]{64}$",
        dockerfile,
        re.MULTILINE,
    )

    assert re.fullmatch(
        r"postgres:[^\s]+@sha256:[0-9a-f]{64}",
        compose["services"]["db"]["image"],
    )


def test_production_dependency_integrity():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "--require-hashes" in dockerfile
    assert "--only-binary=:all:" in dockerfile
    assert "python -m pip check" in dockerfile
    assert "-r requirements.txt" in dockerfile
    assert "requirements-dev" not in dockerfile


def test_production_non_root_user():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert re.search(
        r"^USER 10001$",
        dockerfile,
        re.MULTILINE,
    )


@pytest.mark.parametrize(
    "filename",
    ["requirements.txt", "requirements-dev.txt"],
)
def test_dependency_lock_integrity(filename):
    content = (ROOT / filename).read_text()

    entries = re.split(
        r"(?m)^(?=[a-zA-Z0-9_.-]+==)",
        content,
    )

    packages = [
        entry for entry in entries
        if re.match(r"[a-zA-Z0-9_.-]+==", entry)
    ]

    assert packages

    for package in packages:
        assert re.search(
            r"--hash=sha256:[0-9a-f]{64}",
            package,
        ), package.splitlines()[0]


@pytest.mark.parametrize(
    "filename",
    ["ci.yml", "publish.yml"],
)
def test_workflow_actions_sha_pinned(filename):
    workflow = load_yaml(f".github/workflows/{filename}")
    references = []

    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                references.append(step["uses"])

    assert references

    for reference in references:
        assert re.fullmatch(
            r"[^@\s]+@[0-9a-f]{40}",
            reference,
        )


@pytest.mark.parametrize(
    "filename",
    ["ci.yml", "publish.yml"],
)
def test_checkout_credentials_not_persisted(filename):
    workflow = load_yaml(f".github/workflows/{filename}")
    checkouts = []

    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if step.get("uses", "").startswith(
                "actions/checkout@"
            ):
                checkouts.append(step)

    assert checkouts

    for step in checkouts:
        assert step["with"]["persist-credentials"] == "false"


def test_ci_read_only_permissions():
    workflow = load_yaml(".github/workflows/ci.yml")

    assert workflow["permissions"] == {"contents": "read"}

    for job in workflow["jobs"].values():
        assert job.get("permissions", {"contents": "read"}) == {
            "contents": "read"
        }


def test_publish_permission_isolation():
    workflow = load_yaml(".github/workflows/publish.yml")

    assert workflow["permissions"] == {"contents": "read"}

    validate = workflow["jobs"]["validate"]
    publish = workflow["jobs"]["publish"]

    assert validate.get(
        "permissions", {"contents": "read"}
    ) == {"contents": "read"}

    assert publish["permissions"] == {
        "contents": "read",
        "packages": "write",
    }


def test_publish_release_gate():
    workflow = load_yaml(".github/workflows/publish.yml")
    validate = workflow["jobs"]["validate"]
    publish = workflow["jobs"]["publish"]

    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert publish["needs"] == "validate"
    assert publish["environment"] == "approved-release"

    expected = "github.ref == 'refs/heads/main'"

    assert validate["if"] == expected
    assert publish["if"] == expected


def test_dependabot_ecosystems():
    config = load_yaml(".github/dependabot.yml")

    assert config["version"] == "2"

    assert {
        update["package-ecosystem"]
        for update in config["updates"]
    } == {"pip", "docker", "github-actions"}
