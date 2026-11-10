import os
import re

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_MRN = re.compile(r"MRN[:\s]*\d+", re.IGNORECASE)
_NAME = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")


def _regex_deidentify(note: str) -> str:
    out = _SSN.sub("[SSN]", note)
    out = _MRN.sub("[MRN]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _NAME.sub("[NAME]", out)
    return out


def deidentify_note(note: str) -> tuple[str, dict]:
    try:
        if os.environ.get("USE_MOCK", "1") != "0":
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from openmed import deidentify

        result = deidentify(note, method="mask")
        redacted = getattr(result, "deidentified_text", None)
        if not isinstance(redacted, str):
            raise TypeError("unexpected openmed result")
        entities = getattr(result, "pii_entities", None) or []
        return redacted, {"pii_found": len(entities), "backend": "openmed"}
    except (AttributeError, ImportError, ModuleNotFoundError, TypeError, ValueError):
        return _regex_deidentify(note), {"pii_found": -1, "backend": "regex_fallback"}
