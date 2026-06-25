#!/usr/bin/env python3
"""Validate the error-catalog JSONL files against the importer's Zod contract.

Mirrors innova-backend-serverless/scripts/import-error-catalog.ts so a batch can
be verified locally (regla install-by-user: el agente valida, Victor importa).

Checks, across every out/catalog/NN-*.jsonl file:
  - JSON parses
  - code matches ^[A-Z][A-Z0-9]*_[A-Z][A-Z0-9]*_[A-Z][A-Z0-9_]*$
  - code's domain segment == domain_code
  - required string fields present and non-empty
  - severity in ErrorSeverity, source in ErrorSource, status in ErrorStatus
  - applicable_grades: ints 1..12
  - list fields are lists; optional string fields are strings
  - code uniqueness across ALL files

Exit 0 = clean, 1 = problems found. Prints per-domain counts and grand total.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter

CODE_RX = re.compile(r"^[A-Z][A-Z0-9]*_[A-Z][A-Z0-9]*_[A-Z][A-Z0-9_]*$")
SEVERITY = {"LOW", "MED", "HIGH", "CRITICAL"}
SOURCE = {"CURATED", "LLM_GENERATED", "FIELD_REPORTED"}
STATUS = {"ACTIVE", "DRAFT", "DEPRECATED"}
REQUIRED_STR = ("code", "name", "description", "domain_code", "subdomain_code")
OPTIONAL_STR = ("diagnostic_hint", "remediation", "topic_scope")
LIST_FIELDS = ("applicable_grades", "evidence_required", "references")


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(here, "[0-9][0-9]-*.jsonl")))
    problems: list[str] = []
    seen: dict[str, str] = {}
    per_domain: Counter[str] = Counter()
    total = 0

    for path in files:
        fname = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            for i, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                total += 1
                loc = f"{fname}:{i}"
                try:
                    o = json.loads(line)
                except json.JSONDecodeError as exc:
                    problems.append(f"{loc}: invalid JSON ({exc})")
                    continue
                code = o.get("code", "<missing>")
                for field in REQUIRED_STR:
                    val = o.get(field)
                    if not isinstance(val, str) or not val.strip():
                        problems.append(f"{loc} [{code}]: missing/empty '{field}'")
                if isinstance(code, str) and code != "<missing>":
                    if not CODE_RX.match(code):
                        problems.append(f"{loc} [{code}]: code fails regex")
                    else:
                        domain_seg = code.split("_", 1)[0]
                        if domain_seg != o.get("domain_code"):
                            problems.append(
                                f"{loc} [{code}]: domain segment != domain_code "
                                f"({o.get('domain_code')})"
                            )
                    if code in seen:
                        problems.append(
                            f"{loc} [{code}]: duplicate code (first at {seen[code]})"
                        )
                    else:
                        seen[code] = loc
                if o.get("severity") not in SEVERITY:
                    problems.append(f"{loc} [{code}]: bad severity {o.get('severity')!r}")
                if o.get("source") not in SOURCE:
                    problems.append(f"{loc} [{code}]: bad source {o.get('source')!r}")
                if o.get("status") not in STATUS:
                    problems.append(f"{loc} [{code}]: bad status {o.get('status')!r}")
                for field in LIST_FIELDS:
                    if field in o and not isinstance(o[field], list):
                        problems.append(f"{loc} [{code}]: '{field}' must be a list")
                grades = o.get("applicable_grades", [])
                if isinstance(grades, list):
                    for g in grades:
                        if not isinstance(g, int) or isinstance(g, bool) or not 1 <= g <= 12:
                            problems.append(f"{loc} [{code}]: bad grade {g!r}")
                for field in OPTIONAL_STR:
                    if field in o and not isinstance(o[field], str):
                        problems.append(f"{loc} [{code}]: '{field}' must be a string")
                dom = o.get("domain_code")
                if isinstance(dom, str):
                    per_domain[dom] += 1

    print(f"Files: {len(files)}")
    for dom, n in sorted(per_domain.items(), key=lambda kv: -kv[1]):
        print(f"  {dom:10s} {n}")
    print(f"TOTAL: {total} entries, {len(seen)} unique codes, {len(problems)} problems")
    if problems:
        print("\nPROBLEMS (first 40):")
        for p in problems[:40]:
            print("  " + p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
