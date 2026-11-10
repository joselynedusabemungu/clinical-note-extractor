import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("USE_MOCK", "1")

from extractor import extract


def _load(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _norm_dx(s):
    return s.lower().replace("-", " ").strip()


def _norm_dose(s):
    return re.sub(r"\s+", "", s or "").lower()


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def main():
    notes = {r["id"]: r["note"] for r in _load(HERE / "data" / "notes.jsonl")}
    gold = _load(HERE / "data" / "gold.jsonl")
    cols = [
        "diag_precision",
        "diag_recall",
        "med_name_recall",
        "dose_exact",
        "followup_exact",
        "failed",
        "escalated",
        "rag_unsupported_caught",
        "coverage",
        "unsafe_answered",
    ]
    vals = {c: [] for c in cols}

    for g in gold:
        ext, _err = extract(notes[g["id"]])
        failed = ext is None
        vals["failed"].append(1.0 if failed else 0.0)
        if failed:
            for c in (
                "escalated",
                "rag_unsupported_caught",
                "coverage",
                "unsafe_answered",
            ):
                vals[c].append(0.0)
            continue

        pred_dx = {_norm_dx(d.description) for d in ext.diagnoses}
        gold_dx = {_norm_dx(d) for d in g["diagnoses"]}
        if pred_dx:
            vals["diag_precision"].append(len(pred_dx & gold_dx) / len(pred_dx))
        if gold_dx:
            vals["diag_recall"].append(len(pred_dx & gold_dx) / len(gold_dx))

        pred_meds = {m.name.lower(): _norm_dose(m.dose) for m in ext.medications}
        gold_meds = {m["name"].lower(): _norm_dose(m["dose"]) for m in g["medications"]}
        dose_exact = 1.0
        if gold_meds:
            vals["med_name_recall"].append(
                len(set(pred_meds) & set(gold_meds)) / len(gold_meds)
            )
            dose_exact = sum(
                1 for n, d in gold_meds.items() if pred_meds.get(n) == d
            ) / len(gold_meds)
            vals["dose_exact"].append(dose_exact)

        vals["followup_exact"].append(
            1.0 if len(ext.follow_ups) == g["follow_ups"] else 0.0
        )
        escalated = 1.0 if ext.needs_human_review else 0.0
        vals["escalated"].append(escalated)
        vals["rag_unsupported_caught"].append(
            1.0 if any(m.rag_verified is False for m in ext.medications) else 0.0
        )
        vals["coverage"].append(1.0 - escalated)
        vals["unsafe_answered"].append(
            1.0 if (not escalated and dose_exact < 1.0) else 0.0
        )

    print(f"{'metric':<26}{'value':>8}")
    print("-" * 34)
    for c in cols:
        print(f"{c:<26}{_mean(vals[c]):>8.3f}")
    print(f"notes evaluated: {len(gold)}")


if __name__ == "__main__":
    main()
