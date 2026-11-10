# Design

## 1. Three failure modes
- **Hallucination:** an invented or wrong dose, code, or condition looks like fact once it is in a structured record.
- **Omission:** a missed medication or diagnosis silently drops information a clinician would rely on.
- **Schema drift:** output that is almost-but-not-quite the expected shape breaks downstream systems or gets coerced into wrong values.

## 2. Three layers mapped to them
- **Hallucination → verification layer:** `rag.py` checks each dose against retrieved FDA label text; unverified doses are downgraded and escalated.
- **Omission → evaluation layer:** gold labels and recall metrics measure what is missed; negation handling prevents the opposite error of extracting what was denied.
- **Schema drift → schema layer:** Pydantic v2 models with Literal confidences and Optional fields reject malformed output; structured-output parsing constrains the LLM to the same schema.

## 3. Abstention policy
`decide_abstention` escalates to human review on any of three signals, in order: (1) a medication's dose failed RAG verification, (2) any field carries `low` confidence, (3) a diagnosis or medication appears in the note after a negation word (no/not/denies/without). A final dose-format pass escalates malformed doses. Escalation is the default for ambiguity; a medication with no stated dose is not treated as a failure (nothing to verify).

## 4. Evaluation discipline
Gold labels make claims falsifiable. Adversarial probes (n6: a deliberately implausible dose; negation notes) test the failure modes directly instead of the happy path. Accuracy alone rewards confident answers; **coverage** (what is auto-accepted) and **unsafe_answered** (auto-accepted with a wrong dose) show whether the system knows when not to answer, which is the property that matters in healthcare.

## 5. Tradeoffs
- **No vector DB:** retrieval is keyed by drug name; a JSON cache is simpler and inspectable. Cost: no semantic retrieval.
- **Mock default:** the project runs offline with no key, so anyone can reproduce results. Cost: the mock extractor and fallback verifier are weak; in mock mode the n6 catch comes from a missing label, not dose reasoning.
- **Curated eval set:** six hand-written notes are quick to audit but statistically meaningless as an accuracy estimate.

## 6. With more time
- pgvector over DailyMed for semantic retrieval across label sections (including brand names and combination products).
- A real clinician review loop that feeds corrections back into the gold set.
- FHIR output (MedicationStatement, Condition) for interoperability.
