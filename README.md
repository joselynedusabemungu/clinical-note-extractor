# Clinical Note Extractor

Turns unstructured clinical prose into validated, structured JSON (diagnoses, medications, follow-ups) with per-field confidence, FDA-label dose verification, on-device de-identification, an audit log, and an eval harness, and it abstains when it is not sure.

## The problem

Unstructured clinical text is one of the biggest bottlenecks in healthcare data. LLMs can read it, but the failure mode that matters is the *confident wrong answer*: an invented dose or a negated condition extracted as present. This project treats "I don't know" as a first-class output.

## What it does

Input:

```
67-year-old male with hypertension and type 2 diabetes. Started on metformin 500 mg twice daily. Follow up in 3 months.
```

Output (mock backend, no cached FDA label, so the dose cannot be verified and the note is escalated):

```json
{
  "patient_age": 67,
  "patient_sex": "male",
  "diagnoses": [
    {"description": "hypertension", "icd10_hint": null, "confidence": "high"},
    {"description": "type 2 diabetes", "icd10_hint": null, "confidence": "high"}
  ],
  "medications": [
    {"name": "metformin", "dose": "500 mg", "frequency": "twice daily", "route": null,
     "confidence": "low", "rag_verified": false, "rag_context": "no FDA label retrieved"}
  ],
  "follow_ups": [{"action": "follow up", "timeframe": "in 3 months", "confidence": "high"}],
  "needs_human_review": true,
  "deidentified": true,
  "abstention_reason": "rag_verification_failed"
}
```

## Architecture

```
 note ──► PRIVACY ──► EXTRACTION ──► SAFETY ──► result
          deidentify   LLM / mock     RAG dose check (openFDA)
          (on-device)  Pydantic       abstention policy:
                       validation     RAG verdict, confidence, negation
                                      dose-format sanity pass

 INFRASTRUCTURE: FastAPI (api) · Streamlit (web) · SQLite audit log
                 (note hash only) · eval harness · Docker Compose
```

## Data privacy

- De-identification (`privacy.py`) runs before any LLM call, in-process. OpenMed is used when importable, with a regex fallback otherwise.
- The audit log stores a 16-character SHA-256 prefix of the note, never the note itself.
- Intended for synthetic data only.

## RAG

For each extracted medication with a dose, `rag.py` fetches the FDA label from openFDA, caches it as JSON under `drug_cache/<drug>.json`, takes the `dosage_and_administration` section, and asks the LLM whether the extracted dose is SUPPORTED, NOT_SUPPORTED, or AMBIGUOUS. Anything other than SUPPORTED lowers confidence and escalates the note.

There is no vector database on purpose: lookups are keyed by drug name, so a directory of JSON files is simpler, inspectable, and sufficient. A vector store would matter once retrieval is by *meaning* over many documents.

## Evaluation

`docker compose --profile evals run --rm evals` (or `USE_MOCK=1 python backend/evals/run_evals.py`) prints, in mock mode with no cached FDA labels (verified run, 6 notes, 5/5 tests passing):

```
metric                       value
----------------------------------
diag_precision               1.000
diag_recall                  1.000
med_name_recall              1.000
dose_exact                   0.750
followup_exact               1.000
failed                       0.000
escalated                    0.667
rag_unsupported_caught       0.667
coverage                     0.333
unsafe_answered              0.000
notes evaluated: 6
```

Per-note outcome in this run: n1, n3, n4, n6 escalated (`rag_verification_failed`, no label cached); n2 and n5 (no medications) auto-accepted. `dose_exact` is 0.750 because n6's note states 2000 mg while its gold label says 1000 mg; the extractor reported what the note says and the note was escalated, so `unsafe_answered` stays 0.

- `diag_precision` / `diag_recall`: set overlap of diagnoses (lowercased, hyphens as spaces).
- `med_name_recall`, `dose_exact`: gold medications found, and gold doses matched exactly.
- `followup_exact`: follow-up count equals gold.
- `failed`: extraction raised an error.
- `escalated`: sent to human review. `coverage` is its complement (the auto-accept rate).
- `rag_unsupported_caught`: a medication was flagged `rag_verified=False`. This is the hallucination-catch rate; note n6 (2000 mg metformin, gold 1000 mg) is the deliberate probe.
- `unsafe_answered`: **the most important number.** A note that was auto-accepted (not escalated) while a dose was wrong. It should be 0.

Reading the numbers in mock mode: with no cached FDA labels every dose is unverifiable, so every note with a medication is escalated. That drives `unsafe_answered` to 0 and `rag_unsupported_caught` above 0, but for the blunt reason "no label", not because the system judged 2000 mg implausible. Pre-populate `drug_cache/` or run with `USE_MOCK=0` to exercise real verification.

## Quick start

```bash
cp .env.example .env
docker compose up              
docker compose --profile evals run --rm evals
curl -X POST localhost:8000/extract -H 'Content-Type: application/json' \
  -d '{"note": "67M with HTN. Metformin 500 mg BID. F/u 3 mo."}'
```

Tests (no network): `USE_MOCK=1 pytest backend/tests/`

To use a real model, set `USE_MOCK=0` and `OPENAI_API_KEY`.

## Limitations

- Synthetic data only. Not for clinical use. No authentication on the API.
- The eval set is six notes: it demonstrates the harness, it does not estimate real-world accuracy.
- The mock extractor is a handful of regexes covering the eval vocabulary, not a clinical NLP system.
- The fallback dose verifier (used in mock mode, and if the LLM call fails) only checks that a dose is well-formed. It accepts "2000 mg".
- No vector database; retrieval is by drug-name key only, and openFDA lookup by generic name can miss brand names or combination products.
- Only the first `dosage_and_administration` entry (2000 chars) is used, so dose context can be truncated.
- The regex de-identification fallback misses many identifiers (addresses, dates, lowercase names). In mock mode OpenMed runs offline, so it only works if its model is already cached; otherwise the regex fallback is used.
- ICD-10 codes are only passed through if stated; none are inferred.
- Medications with no stated dose are not RAG-checked.

## Stack

- Python 3.11, Pydantic v2
- OpenAI Python SDK (structured output) with a deterministic mock fallback
- openFDA API, cached to local JSON
- OpenMed for on-device de-identification (regex fallback)
- FastAPI + uvicorn, Streamlit
- SQLite audit log
- pytest
- Docker + Docker Compose (api, web, evals)