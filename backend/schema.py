from typing import Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["high", "medium", "low"]


class Medication(BaseModel):
    name: str = Field(
        description="Medication name exactly as stated in the note (generic preferred)."
    )
    dose: str | None = Field(
        default=None,
        description="Dose as stated, e.g. '500 mg'. Null if not stated. Never infer a dose.",
    )
    frequency: str | None = Field(
        default=None,
        description="Frequency as stated, e.g. 'twice daily'. Null if not stated.",
    )
    route: str | None = Field(
        default=None,
        description="Route of administration as stated, e.g. 'oral'. Null if not stated.",
    )
    confidence: Confidence = Field(
        default="medium",
        description="Confidence in this medication entry: high, medium, or low. Use low for unusual doses.",
    )
    rag_verified: bool | None = Field(
        default=None,
        description="Set by the system after checking the dose against the FDA label. Leave null.",
    )
    rag_context: str | None = Field(
        default=None,
        description="Set by the system: FDA label excerpt used for verification (max 500 chars). Leave null.",
    )

    @field_validator("rag_context")
    @classmethod
    def _truncate_context(cls, v: str | None) -> str | None:
        return v[:500] if v is not None else None


class Diagnosis(BaseModel):
    description: str = Field(
        description="Diagnosis or problem as stated in the note. Do not extract negated conditions."
    )
    icd10_hint: str | None = Field(
        default=None,
        description="ICD-10 code only if explicitly stated in the note. Otherwise null. Never invent codes.",
    )
    confidence: Confidence = Field(
        default="medium",
        description="Confidence in this diagnosis entry: high, medium, or low.",
    )


class FollowUp(BaseModel):
    action: str = Field(
        description="Follow-up action as stated, e.g. 'follow up' or 'cardiology referral'."
    )
    timeframe: str | None = Field(
        default=None,
        description="Timeframe as stated, e.g. 'in 3 months'. Null if not stated. Never invent dates.",
    )
    confidence: Confidence = Field(
        default="medium",
        description="Confidence in this follow-up entry: high, medium, or low.",
    )


class ClinicalExtraction(BaseModel):
    patient_age: int | None = Field(
        default=None, description="Patient age in years if stated, else null."
    )
    patient_sex: Literal["male", "female", "other", "unknown"] | None = Field(
        default=None, description="Patient sex if stated, else null."
    )
    diagnoses: list[Diagnosis] = Field(
        default_factory=list,
        description="Affirmed diagnoses only. Empty list if none or all negated.",
    )
    medications: list[Medication] = Field(
        default_factory=list,
        description="Medications the patient is taking or was started on. Empty if none or negated.",
    )
    follow_ups: list[FollowUp] = Field(
        default_factory=list, description="Follow-up actions stated in the note."
    )
    needs_human_review: bool = Field(
        default=False,
        description="Set by the system when the extraction should be reviewed by a human.",
    )
    deidentified: bool = Field(
        default=False,
        description="Set by the system: true once the note was de-identified before extraction.",
    )
    abstention_reason: str | None = Field(
        default=None,
        description="Set by the system: why the extraction was escalated, else null.",
    )
