"""Validate the committed claimant AI regression manifest without calling an LLM."""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_CASES = {
    "qa-before-intake", "unsupported-policy", "mixed-turn", "dynamic-requirements",
    "explicit-submit", "correction", "evidence-uncertain", "tenant-boundary",
}

manifest_path = Path(__file__).resolve().parents[1] / "evaluations" / "claimant_regression_cases.json"
data = json.loads(manifest_path.read_text(encoding="utf-8"))

if not isinstance(data.get("manifest_version"), str):
    raise SystemExit("manifest_version must be a string")

cases = data.get("cases")
if not isinstance(cases, list) or not cases:
    raise SystemExit("cases must be a non-empty list")

ids = {str(item.get("id")) for item in cases if isinstance(item, dict)}
missing = REQUIRED_CASES - ids
if missing:
    raise SystemExit(f"Missing required regression cases: {sorted(missing)}")

for item in cases:
    if not isinstance(item, dict):
        raise SystemExit("Every regression case must be an object")
    if not str(item.get("input") or "").strip():
        raise SystemExit(f"Case {item.get("id")} has no input")
    if not isinstance(item.get("properties"), list) or not item["properties"]:
        raise SystemExit(f"Case {item.get("id")} must declare expected properties")

print(f"AI evaluation manifest valid: {len(cases)} cases, version {data['manifest_version']}")
