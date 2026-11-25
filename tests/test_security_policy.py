import importlib.util
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SPEC = importlib.util.spec_from_file_location(
    "security_evaluator",
    ROOT / "scripts/security/evaluate.py",
)

policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)

REGISTER = ROOT / "config/security/exceptions.json"

DIGEST = "sha256:" + "a" * 64

TODAY = date(2026, 11, 24)


def synthetic_entry(**overrides):
    entry = {
        "exception_id": "TEST-EXC-001",
        "image": "application",
        "digest": DIGEST,
        "approved_on": "2026-11-24",
        "expires_on": "2026-12-24",
        "approved_by": "Project owner",
        "cve": "CVE-2026-00001",
        "package": "examplelib",
        "installed_version": "1.0.0",
        "severity": "HIGH",
        "target_type": "debian",
        "target_path": None,
        "justification": "Synthetic test exception.",
        "controls": ["Control one", "Control two"],
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def entries():
    return [
        synthetic_entry(),
        synthetic_entry(
            exception_id="TEST-EXC-002",
            cve="CVE-2026-00002",
            target_type="gobinary",
            target_path="usr/local/bin/helper",
        ),
    ]


def test_production_register_is_valid_and_empty():
    assert policy.load_exceptions(REGISTER) == []


def make_report(entry, fixed="patched"):
    return {
        "SchemaVersion": 2,
        "Results": [
            {
                "Target": (
                    entry["target_path"]
                    or "application.tar (debian 13.8)"
                ),
                "Type": entry["target_type"],
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": entry["cve"],
                        "PkgName": entry["package"],
                        "InstalledVersion": entry["installed_version"],
                        "Severity": entry["severity"],
                        "FixedVersion": fixed,
                    }
                ],
            }
        ],
    }


def assess(report, entries, **overrides):
    arguments = {
        "image": "application",
        "digest": DIGEST,
        "today": TODAY,
    }

    arguments.update(overrides)

    return policy.evaluate(
        report,
        entries,
        **arguments,
    )


def test_each_approved_exception(entries):
    for entry in entries:
        summary = assess(make_report(entry), entries)

        assert len(summary["accepted"]) == 1
        assert not summary["blockers"]
        assert not summary["expired"]


def test_expired_exceptions_block(entries):
    summary = assess(
        make_report(entries[0]),
        entries,
        today=date(2026, 12, 24),
    )

    assert len(summary["blockers"]) == 1
    assert len(summary["expired"]) == len(entries)
    assert not summary["accepted"]


def test_future_approval_is_invalid(entries):
    summary = assess(
        make_report(entries[0]),
        entries,
        today=date(2026, 11, 23),
    )

    assert summary["blockers"]
    assert summary["expired"]
    assert not summary["accepted"]


def test_wrong_image_digest_blocks(entries):
    summary = assess(
        make_report(entries[0]),
        entries,
        digest="sha256:" + "0" * 64,
    )

    assert len(summary["blockers"]) == 1
    assert not summary["accepted"]


def test_exception_cannot_apply_to_other_images(entries):
    summary = assess(
        make_report(entries[0]),
        entries,
        image="unrelated",
    )

    assert len(summary["blockers"]) == 1
    assert not summary["accepted"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("VulnerabilityID", "CVE-2099-99999"),
        ("PkgName", "different-package"),
        ("InstalledVersion", "different-version"),
    ],
)
def test_exception_scope_mismatch_blocks(entries, field, value):
    report = make_report(entries[0])
    report["Results"][0]["Vulnerabilities"][0][field] = value

    summary = assess(report, entries)

    assert len(summary["blockers"]) == 1
    assert not summary["accepted"]


def test_wrong_executable_path_blocks(entries):
    report = make_report(entries[1])
    report["Results"][0]["Target"] = "usr/local/bin/other"

    summary = assess(report, entries)

    assert len(summary["blockers"]) == 1
    assert not summary["accepted"]


def test_wrong_target_type_blocks(entries):
    report = make_report(entries[0])
    report["Results"][0]["Type"] = "other"

    summary = assess(report, entries)

    assert len(summary["blockers"]) == 1
    assert not summary["accepted"]


@pytest.mark.parametrize(
    "severity,fixed,category",
    [
        ("CRITICAL", "", "blockers"),
        ("CRITICAL", "patched", "blockers"),
        ("HIGH", "patched", "blockers"),
        ("HIGH", "", "monitor"),
        ("MEDIUM", "patched", "reported"),
        ("LOW", "", "reported"),
        ("UNKNOWN", "", "reported"),
    ],
)
def test_vulnerability_thresholds(entries, severity, fixed, category):
    entry = deepcopy(entries[0])
    entry["cve"] = "CVE-2099-99999"
    entry["severity"] = severity

    summary = assess(make_report(entry, fixed), entries)

    assert len(summary[category]) == 1
    assert not summary["accepted"]


@pytest.mark.parametrize(
    "report",
    [
        {},
        {"SchemaVersion": 1, "Results": []},
        {"SchemaVersion": 2},
        {"SchemaVersion": 2, "Results": []},
        {"SchemaVersion": 2, "Results": [{}]},
    ],
)
def test_invalid_reports_fail_closed(entries, report):
    with pytest.raises(ValueError):
        assess(report, entries)


def test_clean_report_passes(entries):
    report = {
        "SchemaVersion": 2,
        "Results": [
            {
                "Target": "application.tar",
                "Type": "debian",
                "Vulnerabilities": [],
            }
        ],
    }

    summary = assess(report, entries)

    assert all(not findings for findings in summary.values())
