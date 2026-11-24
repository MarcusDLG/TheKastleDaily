"""Evaluate Trivy findings against the approved security policy."""

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path


def load_exceptions(path):
    data = json.loads(Path(path).read_text())

    if data["schema_version"] != 1:
        raise ValueError("Unsupported exception schema")

    entries = data["exceptions"]
    if not isinstance(entries, list):
        raise ValueError("Invalid exception register")

    seen = set()

    for entry in entries:
        for field in (
            "exception_id",
            "image",
            "digest",
            "cve",
            "package",
            "installed_version",
            "severity",
            "target_type",
            "justification",
            "approved_by",
        ):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ValueError(f"Invalid exception field: {field}")

        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry["digest"]):
            raise ValueError("Invalid exception digest")

        if not re.fullmatch(r"CVE-\d{4}-\d{4,}", entry["cve"]):
            raise ValueError("Invalid CVE identifier")

        if entry["severity"] not in {"HIGH", "CRITICAL"}:
            raise ValueError("Invalid exception severity")

        approved = date.fromisoformat(entry["approved_on"])
        expires = date.fromisoformat(entry["expires_on"])

        if not 0 < (expires - approved).days <= 30:
            raise ValueError("Invalid exception duration")

        if not entry["controls"]:
            raise ValueError("Missing compensating controls")

        key = (
            entry["image"],
            entry["digest"],
            entry["cve"],
            entry["package"],
            entry["installed_version"],
            entry["severity"],
            entry["target_type"],
            entry["target_path"],
        )

        if key in seen:
            raise ValueError("Duplicate exception")

        seen.add(key)

    return entries


def matches(entry, result, vuln, image, digest):
    return (
        entry["image"] == image
        and entry["digest"] == digest
        and entry["cve"] == vuln["VulnerabilityID"]
        and entry["package"] == vuln["PkgName"]
        and entry["installed_version"] == vuln["InstalledVersion"]
        and entry["severity"] == vuln["Severity"]
        and entry["target_type"] == result["Type"]
        and (
            entry["target_path"] is None
            or entry["target_path"] == result["Target"]
        )
    )


def evaluate(report, entries, image, digest, today):
    if report.get("SchemaVersion") != 2:
        raise ValueError("Unsupported Trivy report schema")

    results = report.get("Results")

    if not isinstance(results, list) or not results:
        raise ValueError("Missing Trivy scan results")

    summary = {
        "accepted": [],
        "blockers": [],
        "monitor": [],
        "reported": [],
        "expired": [],
    }

    for entry in entries:
        if entry["image"] != image:
            continue

        approved = date.fromisoformat(entry["approved_on"])
        expires = date.fromisoformat(entry["expires_on"])

        if not approved <= today < expires:
            summary["expired"].append(entry["cve"])

    for result in results:
        if not result.get("Target") or not result.get("Type"):
            raise ValueError("Invalid scan target")

        vulnerabilities = result.get("Vulnerabilities") or []

        if not isinstance(vulnerabilities, list):
            raise ValueError("Invalid vulnerability list")

        for vuln in vulnerabilities:
            severity = vuln["Severity"]

            if severity not in {
                "UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"
            }:
                raise ValueError("Unknown severity classification")

            fixed = bool(
                (vuln.get("FixedVersion") or "").strip()
            )

            finding = {
                "cve": vuln["VulnerabilityID"],
                "package": vuln["PkgName"],
                "installed_version": vuln["InstalledVersion"],
                "severity": severity,
                "fixed_version": vuln.get("FixedVersion"),
                "target": result["Target"],
            }

            blocking = (
                severity == "CRITICAL"
                or (severity == "HIGH" and fixed)
            )

            if blocking:
                accepted = next(
                    (
                        entry for entry in entries
                        if matches(
                            entry, result, vuln, image, digest
                        )
                        and date.fromisoformat(
                            entry["approved_on"]
                        ) <= today < date.fromisoformat(
                            entry["expires_on"]
                        )
                    ),
                    None,
                )

                if accepted:
                    finding["exception_id"] = accepted["exception_id"]
                    summary["accepted"].append(finding)
                else:
                    summary["blockers"].append(finding)

            elif severity == "HIGH":
                summary["monitor"].append(finding)

            else:
                summary["reported"].append(finding)

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--exceptions", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.digest):
        raise ValueError("Invalid image digest")

    report = json.loads(Path(args.report).read_text())
    entries = load_exceptions(args.exceptions)

    summary = evaluate(
        report,
        entries,
        args.image,
        args.digest,
        datetime.now(timezone.utc).date(),
    )

    Path(args.output).write_text(
        json.dumps(summary, indent=2) + "\n"
    )

    for category, findings in summary.items():
        print(f"{category.upper()}: {len(findings)}")

    return 10 if summary["blockers"] or summary["expired"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
