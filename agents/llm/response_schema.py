from pydantic import BaseModel, Field
from typing import Literal, TypeAlias

# =========================================
# LITERAL VALUES FOR OUTPUT SCHEMAS
# =========================================

Tools: TypeAlias= Literal[
    "clinvar",
    "gnomad",
    "gnomad_gene", 
    "revel_spliceai",
    "spliceai",
    "vep",
    "pubmed",
    "erepo",
    "lovd",
    "functional_evidence"
]

StrengthNote: TypeAlias= Literal[
    "very_strong",
    "strong",
    "moderate",
    "supporting",
    "benign_stand_alone",
    "benign_strong",
    "benign_supporting",
]

Direction: TypeAlias= Literal[
    "functionally_abnormal",
    "functionally_normal",
    "ambiguous"
]

# =========================================
# OUTPUT SCHEMAS
# =========================================
class CheckTechnicalResult(BaseModel):
    passed: bool = Field(
        description="""Whether there are any technical error in the task output, including 
        tool caCOn failures, missing data, API errors, malformed outputs, or status=error. 
            True if there are NO technical error. False if any technical error is detected."""
    )

    error_type: str = Field(
        description="""A brief justifications of why do you think there are/aren't technical errors"""
    )

    feedback: str | None = Field(
        description="""This field is None if the field "pass" is true. If pass is false, 
        provider specific instruction for the Task agent to fix the error."""
    )

class CheckReasoningResult(BaseModel):
    passed: bool = Field(
        description="""Whether the reasoning in the task output is correct. 
            True if there are NO reasoning errors in tool selection, evidence interpretation, 
            or criterion mapping. False if any reasoning error is detected."""
    )

    error_type: str = Field(
        description="""A brief justifications of why do you think there are/aren't reasoning errors"""
    )

    feedback: str | None = Field(
        description="""This field is None if the field "pass" is true. If pass is false, 
        provider specific instruction for the Task agent to fix the error."""
    )


class ToolDecision(BaseModel):
    tool: Tools = Field(
        description="""The name of the tool that you think is approriate 
        for evaluating this criterion"""
    )

    reason: str = Field(
        description="""One sentence explaining why this tool is appropriate."""
    )

class TaskInterpretation(BaseModel):
    evidence: str = Field(
        description="""A concise summary of the raw evidence retrieved from the tool."""
    )

    reasoning: str = Field(
        description="""Explanation of how the retrieved evidence maps to the ACMG 
        criterion and why the criterion applies or does not apply."""
    )

    applies: bool = Field(
        description="""Whether the criterion applies based on the evidence. Must be a real boolean,
        not a string. If the status is error, set applies to false."""
    )

    applied_strength: StrengthNote | None = Field(
        description=""""Strength level for the criterion if it applies. 
        Use None when the criterion does not apply. If the status is error, 
        set applied_strength to None."""
    )

    status: Literal["complete", "error"] = Field(
        description="Use 'complete' if the interpretation succeeded. Use 'error' only if the task could not be completed."
    )

class FunctionalPaperFiltering(BaseModel):
    is_functional: bool = Field(
        description="""Whether the paper contains any functional evidence regardless of the variant.
        true if abstract reports a qualifying functional experiment for ANY genetic variant, mutation, allele, or mutant.
        false otherwise."""
    )

    justification: str = Field(
        description="""1-3 sentence explaining why do you think the paper contains functional experiments based on the abstract"""
    )

class FunctionalExperiment(BaseModel):
    effect_direction: Direction = Field(
        description="""Functional impact of the tested variant relative 
        to the normal comparator. If you think the is mixed, intermediate,
        or you cannot determine whether is it functionally_normal or 
        functionally_abnormal, you should return ambiguous."""
    )

    assay_type: str | None = Field(
        description=(
            "Laboratory assay or experimental method used to test the variant's "
            "functional effect, such as a signaling, binding, splicing, "
            "localization, or enzyme-activity assay."
            "Returns None if the assay_type is unclear from the paper."
        )
    )

    system: str | None = Field(
        description=(
            "Biological or experimental environment in which the assay was "
            "performed, such as a cell line, patient-derived tissue, animal "
            "model, or purified protein."
            "Returns none if the system is unclear from the paper"
        )
    )

    readout: str | None = Field(
        description=(
            "Specific functional endpoint measured by the assay, including "
            "measurement units when reported."
            "Returns none if the readout is unclear."
        )
    )

    effect_size_and_stats: str | None = Field(
        description=(
            "A summary of quantitative details of the result as reported, such as percentages, "
            "fold changes, p-values, confidence intervals, or replicate counts."
            "Return None if unclear."
        )
    )

    controls_and_validation: str | None = Field(
        description=(
            "Experimental controls, replication, calibration, and assay-validation "
            "details used to assess the reliability of the result."
            "Return None if unclear."
        )
    )

    authors_conclusion: str | None = Field(
        description=(
            "The paper authors' explicit interpretation of the variant's "
            "functional effect."
            "Returns None if unclear"
        )
    )

class FunctionalExperiments(BaseModel):
    experiments: list[FunctionalExperiment] = Field(
        description=(
            "A list of functional experiments across all the functional papers." \
            "Returns empty list if there is no relevant functional experiment found"
        )
    )

    



