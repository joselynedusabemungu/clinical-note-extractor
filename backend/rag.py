import json
import os
import re
from collections.abc import Callable
from pathlib import Path

import requests

FDA_ENDPOINT = os.environ.get("FDA_ENDPOINT", "https://api.fda.gov/drug/label.json")
_DOSE_RE = re.compile(r"^\d+(\.\d+)?\s?(mg|g|mcg|ml|units?)$", re.IGNORECASE)


def _is_mock() -> bool:
    return os.environ.get("USE_MOCK", "1") != "0"


def _cache_dir() -> Path:
    return Path(os.environ.get("RAG_CACHE_DIR", "drug_cache"))


def _cache_path(drug: str) -> Path:
    safe = re.sub(r"[^a-z0-9_-]", "_", drug.lower().strip())
    return _cache_dir() / f"{safe}.json"


def _fda_url(drug: str) -> str:
    return f"{FDA_ENDPOINT}?search=openfda.generic_name:{drug}&limit=1"


def fetch_fda_label(drug: str) -> dict | None:
    path = _cache_path(drug)
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (OSError, TypeError, ValueError):
        return None
    if _is_mock():
        return None
    try:
        resp = requests.get(
            FDA_ENDPOINT,
            params={"search": f"openfda.generic_name:{drug}", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(results[0]))
        return results[0]
    except (OSError, TypeError, ValueError, requests.RequestException):
        return None


def retrieve_dosage_context(drug: str) -> str | None:
    label = fetch_fda_label(drug)
    if not label:
        return None
    sections = label.get("dosage_and_administration")
    if not sections:
        return None
    return str(sections[0])[:2000]


def _fallback_verify(dose: str | None) -> tuple[bool, str]:
    if dose and _DOSE_RE.match(dose.strip()):
        return True, "fallback: dose format valid"
    return False, "fallback: dose format invalid"


def verify_dose_via_llm(
    drug: str,
    dose: str | None,
    context: str | None,
    llm_call: Callable[[str], str],
) -> tuple[bool, str]:
    if context is None:
        return False, "no FDA label retrieved"
    if _is_mock():
        return _fallback_verify(dose)
    prompt = (
        "You are verifying a medication dose against FDA label text.\n"
        f"Drug: {drug}\nExtracted dose: {dose}\n"
        f'FDA dosage and administration text:\n"""\n{context}\n"""\n'
        "Answer with exactly one word: SUPPORTED, NOT_SUPPORTED, or AMBIGUOUS."
    )
    try:
        answer = (llm_call(prompt) or "").strip()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return _fallback_verify(dose)
    token = answer.split()[0].strip(".,:;").upper() if answer else ""
    if token == "SUPPORTED":
        return True, "FDA label confirms dose"
    return False, f"LLM verdict: {token or 'EMPTY'}"


def annotate_with_rag(extraction, llm_call: Callable[[str], str]):
    for med in extraction.medications:
        if med.dose is None:
            continue
        context = retrieve_dosage_context(med.name)
        ok, reason = verify_dose_via_llm(med.name, med.dose, context, llm_call)
        med.rag_verified = ok
        med.rag_context = (context or reason)[:500]
        if not ok:
            med.confidence = "low"
            extraction.needs_human_review = True
    return extraction
