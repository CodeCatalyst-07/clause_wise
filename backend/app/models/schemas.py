"""
ClauseWise — Extraction Schemas (per Document Type)

Each schema is a Pydantic model that defines the structured fields to extract
from a legal document of the corresponding type. These models serve double duty:

  1. They are passed to Gemini's ``response_schema`` parameter so the model
     returns validated, structured JSON — not free-text that we have to parse.
  2. They document, in one place, exactly what fields the system extracts for
     each document category, making the pipeline auditable and extensible.

The ``risk_flags`` field appears on every schema: it asks Gemini to proactively
flag clauses that are unusually one-sided, ambiguous, or worth a user's
attention. This is what makes ClauseWise a *smart* assistant, not just a
mechanical extractor.

To add a new document type:
  1. Create a new Pydantic model here.
  2. Add the corresponding ``DocumentType`` enum member.
  3. Register the mapping in ``EXTRACTION_SCHEMA_MAP`` at the bottom.
"""

from pydantic import BaseModel, Field

from app.models.document_types import DocumentType


# ---------------------------------------------------------------------------
# LEASE
# ---------------------------------------------------------------------------

class LeaseExtraction(BaseModel):
    """Structured fields extracted from a residential or commercial lease."""

    parties: list[str] = Field(
        default_factory=list,
        description="Names of all parties (landlord, tenant, guarantor, etc.).",
    )
    rent_amount: str = Field(
        default="",
        description="Monthly or periodic rent amount including currency.",
    )
    payment_due_date: str = Field(
        default="",
        description="Day of the month or schedule when rent is due.",
    )
    lease_term_start: str = Field(
        default="",
        description="Lease start date (or 'not specified').",
    )
    lease_term_end: str = Field(
        default="",
        description="Lease end date (or 'not specified').",
    )
    security_deposit: str = Field(
        default="",
        description="Security deposit amount and conditions for return.",
    )
    maintenance_obligations: str = Field(
        default="",
        description="Who is responsible for repairs and maintenance.",
    )
    termination_conditions: str = Field(
        default="",
        description="How and when either party can terminate the lease.",
    )
    notable_restrictions: str = Field(
        default="",
        description="Restrictions on use (e.g. no pets, no subletting).",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Plain-language flags for clauses that are one-sided, ambiguous, or noteworthy.",
    )


# ---------------------------------------------------------------------------
# NDA (Non-Disclosure Agreement)
# ---------------------------------------------------------------------------

class NDAExtraction(BaseModel):
    """Structured fields extracted from a non-disclosure agreement."""

    parties: list[str] = Field(
        default_factory=list,
        description="Names of the disclosing and receiving parties.",
    )
    confidentiality_scope: str = Field(
        default="",
        description="What information is considered confidential.",
    )
    duration: str = Field(
        default="",
        description="How long the confidentiality obligation lasts.",
    )
    exceptions_to_confidentiality: str = Field(
        default="",
        description="Carve-outs (e.g. publicly available info, prior knowledge).",
    )
    remedies_for_breach: str = Field(
        default="",
        description="What happens if a party breaches the NDA.",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Plain-language flags for clauses that are one-sided, ambiguous, or noteworthy.",
    )


# ---------------------------------------------------------------------------
# TERMS OF SERVICE
# ---------------------------------------------------------------------------

class TermsOfServiceExtraction(BaseModel):
    """Structured fields extracted from terms of service / user agreements."""

    parties_or_service_name: str = Field(
        default="",
        description="The service provider / platform name and the user designation.",
    )
    data_usage_terms: str = Field(
        default="",
        description="How user data is collected, used, and shared.",
    )
    liability_limitations: str = Field(
        default="",
        description="Caps or exclusions on the provider's liability.",
    )
    dispute_resolution_method: str = Field(
        default="",
        description="Arbitration, mediation, courts, jurisdiction, etc.",
    )
    cancellation_termination_terms: str = Field(
        default="",
        description="How users or the provider can cancel/terminate the account or service.",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Plain-language flags for clauses that are one-sided, ambiguous, or noteworthy.",
    )


# ---------------------------------------------------------------------------
# EMPLOYMENT CONTRACT
# ---------------------------------------------------------------------------

class EmploymentContractExtraction(BaseModel):
    """Structured fields extracted from an employment contract."""

    parties: list[str] = Field(
        default_factory=list,
        description="Employer and employee names.",
    )
    role_or_title: str = Field(
        default="",
        description="Job title or role description.",
    )
    compensation: str = Field(
        default="",
        description="Salary, bonuses, equity, or other compensation details.",
    )
    termination_conditions: str = Field(
        default="",
        description="Conditions under which employment may be terminated.",
    )
    non_compete: str = Field(
        default="",
        description="Non-compete clause details, or 'not present' if absent.",
    )
    benefits: str = Field(
        default="",
        description="Health insurance, PTO, retirement, and other benefits.",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Plain-language flags for clauses that are one-sided, ambiguous, or noteworthy.",
    )


# ---------------------------------------------------------------------------
# OTHER (generic fallback)
# ---------------------------------------------------------------------------

class OtherExtraction(BaseModel):
    """
    Generic extraction schema used when the document type cannot be
    confidently classified. Designed to still produce useful structured
    output for *any* legal document.
    """

    parties: list[str] = Field(
        default_factory=list,
        description="Names of all parties mentioned in the document.",
    )
    key_dates: list[str] = Field(
        default_factory=list,
        description="Important dates (effective date, expiration, deadlines).",
    )
    obligations: list[str] = Field(
        default_factory=list,
        description="Key obligations or duties described in the document.",
    )
    potential_risks: list[str] = Field(
        default_factory=list,
        description="Clauses or conditions that may pose risks to a party.",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Plain-language flags for clauses that are one-sided, ambiguous, or noteworthy.",
    )


# ---------------------------------------------------------------------------
# Schema registry — maps DocumentType → Pydantic extraction model.
# Used by the extraction function in gemini_service.py to pick the right
# schema at runtime without a long if/elif chain.
# ---------------------------------------------------------------------------

EXTRACTION_SCHEMA_MAP: dict[DocumentType, type[BaseModel]] = {
    DocumentType.LEASE: LeaseExtraction,
    DocumentType.NDA: NDAExtraction,
    DocumentType.TERMS_OF_SERVICE: TermsOfServiceExtraction,
    DocumentType.EMPLOYMENT_CONTRACT: EmploymentContractExtraction,
    DocumentType.OTHER: OtherExtraction,
}
