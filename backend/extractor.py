import json
import os
import re

from privacy import deidentify_note
from rag import annotate_with_rag
from schema import ClinicalExtraction, Diagnosis, FollowUp, Medication

SYSTEM_PROMPT = (
    "You are a clinical information extraction system. Extract ONLY what is explicitly "
    "stated in the note. Use null for any missing value. Never invent doses, ICD-10 codes, "
    "or dates. Do not extract negated conditions or medications (e.g. 'no history of X', "
    "'not on Y'). Assign a per-field confidence of high, medium, or low; use low when the "
    "note is ambiguous or a dose is unusual. Return JSON matching the provided schema."
)

_EX_A_NOTE = "58-year-old female with asthma. Albuterol 90 mcg inhaled every 4 hours as needed. Follow up in 6 weeks."
_EX_A_OUT = {
    "patient_age": 58,
    "patient_sex": "female",
    "diagnoses": [{"description": "asthma", "icd10_hint": None, "confidence": "high"}],
    "medications": [
        {
            "name": "albuterol",
            "dose": "90 mcg",
            "frequency": "every 4 hours as needed",
            "route": "inhaled",
            "confidence": "high",
        }
    ],
    "follow_ups": [
        {"action": "follow up", "timeframe": "in 6 weeks", "confidence": "high"}
    ],
}
_EX_B_NOTE = "Patient on metformin 5000 mg daily for diabetes. Follow up in 1 month."
_EX_B_OUT = {
    "patient_age": None,
    "patient_sex": None,
    "diagnoses": [
        {"description": "diabetes", "icd10_hint": None, "confidence": "high"}
    ],
    "medications": [
        {
            "name": "metformin",
            "dose": "5000 mg",
            "frequency": "daily",
            "route": None,
            "confidence": "low",
        }
    ],
    "follow_ups": [
        {"action": "follow up", "timeframe": "in 1 month", "confidence": "high"}
    ],
}
_EX_C_NOTE = "No history of diabetes. Not on metformin."
_EX_C_OUT = {
    "patient_age": None,
    "patient_sex": None,
    "diagnoses": [],
    "medications": [],
    "follow_ups": [],
}

FEW_SHOT_EXAMPLES = (
    "Example 1 (normal note):\n"
    f'Note: """{_EX_A_NOTE}"""\nOutput: {json.dumps(_EX_A_OUT)}\n\n'
    "Example 2 (unusual dose, hallucination-prone: keep it as stated, confidence low):\n"
    f'Note: """{_EX_B_NOTE}"""\nOutput: {json.dumps(_EX_B_OUT)}\n\n'
    "Example 3 (explicit negation: extract nothing):\n"
    f'Note: """{_EX_C_NOTE}"""\nOutput: {json.dumps(_EX_C_OUT)}\n'
)

_DOSE_RE = re.compile(r"^\d+(\.\d+)?\s?(mg|g|mcg|ml|units?)$", re.IGNORECASE)
_NEG_RE = re.compile(r"\b(no|not|denies|denied|without)\b", re.IGNORECASE)


def _schema_json() -> str:
    return json.dumps(ClinicalExtraction.model_json_schema())


def _build_user_prompt(note: str) -> str:
    return (
        f"JSON schema:\n{_schema_json()}\n\n"
        f"{FEW_SHOT_EXAMPLES}\n"
        f'Now extract from this note:\n"""\n{note}\n"""'
    )


def _use_mock() -> bool:
    return os.environ.get("USE_MOCK", "1") != "0"


def _call_openai(note: str) -> dict:
    from openai import OpenAI

    client = OpenAI()
    resp = client.beta.chat.completions.parse(
        model=os.environ.get("MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(note)},
        ],
        response_format=ClinicalExtraction,
        temperature=0,
    )
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        raise ValueError("model returned no parsed output (refusal or truncation)")
    return parsed.model_dump()


def _call_openai_text(prompt: str) -> str:
    from openai import OpenAI

    resp = OpenAI().chat.completions.create(
        model=os.environ.get("MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10,
    )
    return resp.choices[0].message.content or ""


_DX_PATTERNS = [
    (re.compile(r"type (?:2|ii) diabetes", re.IGNORECASE), "type 2 diabetes"),
    (re.compile(r"diabetes", re.IGNORECASE), "diabetes"),
    (re.compile(r"hypertension|\bhtn\b", re.IGNORECASE), "hypertension"),
    (re.compile(r"chest pain", re.IGNORECASE), "chest pain"),
    (re.compile(r"headache", re.IGNORECASE), "headache"),
]
_MED_RE = re.compile(
    r"\b([A-Za-z][A-Za-z]{2,})\s+(\d+(?:\.\d+)?\s?(?:mg|g|mcg|ml|units?))\b",
    re.IGNORECASE,
)
_MED_STOP = {
    "started",
    "with",
    "and",
    "the",
    "patient",
    "take",
    "taking",
    "dose",
    "daily",
    "increased",
    "decreased",
    "continue",
    "continued",
    "then",
    "from",
    "for",
    "was",
}
_FREQ_RE = re.compile(
    r"^\s*(twice daily|once daily|three times daily|daily|bid|tid|qid|qd|at bedtime)",
    re.IGNORECASE,
)
_FU_RE = re.compile(r"\b(follow[- ]?up|f/u)\b(.*)", re.IGNORECASE)
_TIME_RE = re.compile(
    r"(in\s+)?(\d+\s*(?:days?|weeks?|months?|mo|years?|yr)s?\b|as needed)",
    re.IGNORECASE,
)


def _sentences(note: str):
    return [s for s in re.split(r"(?<=[.!?])\s+", note.strip()) if s]


def _negated_before(sentence: str, idx: int) -> bool:
    return bool(_NEG_RE.search(sentence[:idx]))


def _call_mock(note: str) -> dict:
    ext = ClinicalExtraction(deidentified=True)
    m = re.search(r"\b(\d{1,3})[- ]year[- ]old\b", note, re.IGNORECASE) or re.search(
        r"\b(\d{1,3})\s?[MF]\b", note
    )
    if m:
        ext.patient_age = int(m.group(1))
    if re.search(r"\bfemale\b|\b\d{1,3}\s?F\b", note):
        ext.patient_sex = "female"
    elif re.search(r"\bmale\b|\b\d{1,3}\s?M\b", note):
        ext.patient_sex = "male"

    seen_dx, seen_med = set(), set()
    for sent in _sentences(note):
        for pat, label in _DX_PATTERNS:
            if label == "diabetes" and "type 2 diabetes" in {d for d in seen_dx}:
                continue
            hit = pat.search(sent)
            if hit and not _negated_before(sent, hit.start()) and label not in seen_dx:
                seen_dx.add(label)
                ext.diagnoses.append(Diagnosis(description=label, confidence="high"))
        for hit in _MED_RE.finditer(sent):
            name = hit.group(1).lower()
            if (
                name in _MED_STOP
                or _negated_before(sent, hit.start())
                or name in seen_med
            ):
                continue
            seen_med.add(name)
            freq = _FREQ_RE.match(sent[hit.end() :])
            route = (
                "oral"
                if re.search(r"\b(po|oral|by mouth)\b", sent, re.IGNORECASE)
                else None
            )
            ext.medications.append(
                Medication(
                    name=name,
                    dose=hit.group(2).strip(),
                    frequency=freq.group(1).lower() if freq else None,
                    route=route,
                    confidence="high",
                )
            )
        fu = _FU_RE.search(sent)
        if fu and not _negated_before(sent, fu.start()):
            t = _TIME_RE.search(fu.group(2))
            timeframe = None
            if t:
                timeframe = ("in " if t.group(1) else "") + t.group(2)
            ext.follow_ups.append(
                FollowUp(action="follow up", timeframe=timeframe, confidence="high")
            )
    return ext.model_dump()


def call_llm(note: str) -> dict:
    return _call_mock(note) if _use_mock() else _call_openai(note)


def _verify_call(prompt: str) -> str:
    """LLM callable handed to the RAG verifier (never invoked in mock mode)."""
    if _use_mock():
        raise RuntimeError("mock mode: no LLM verification")
    return _call_openai_text(prompt)


def _terms_for(ext: ClinicalExtraction):
    terms = [m.name.lower() for m in ext.medications]
    for d in ext.diagnoses:
        desc = d.description.lower()
        terms.append(desc)
        if "hypertension" in desc:
            terms.append("htn")
    return terms


def decide_abstention(ext: ClinicalExtraction, note: str) -> tuple[bool, str | None]:
    if any(m.rag_verified is False for m in ext.medications):
        return True, "rag_verification_failed"
    fields = [*ext.diagnoses, *ext.medications, *ext.follow_ups]
    if any(f.confidence == "low" for f in fields):
        return True, "low_confidence_field"
    for sent in _sentences(note):
        low = sent.lower()
        for term in _terms_for(ext):
            idx = low.find(term)
            if idx != -1 and _negated_before(low, idx):
                return True, "negation_mismatch"
    return False, None


def extract(note: str) -> tuple[ClinicalExtraction | None, str | None]:
    redacted, _ = deidentify_note(note)
    try:
        ext = ClinicalExtraction.model_validate(call_llm(redacted))
    except (AttributeError, RuntimeError, TypeError, ValueError) as e:
        return None, f"extraction_failed: {type(e).__name__}: {e}"
    try:
        ext = annotate_with_rag(ext, llm_call=_verify_call)
    except (AttributeError, RuntimeError, TypeError, ValueError) as e:
        return None, f"extraction_failed: {type(e).__name__}: {e}"

    abstain, reason = decide_abstention(ext, redacted)
    if abstain:
        ext.needs_human_review = True
        ext.abstention_reason = reason

    for med in ext.medications:
        if med.dose is not None and not _DOSE_RE.match(med.dose.strip()):
            med.confidence = "low"
            ext.needs_human_review = True
            ext.abstention_reason = ext.abstention_reason or "malformed_dose"
    if ext.needs_human_review and not ext.abstention_reason:
        ext.abstention_reason = "model_requested_review"
    ext.deidentified = True
    return ext, None
