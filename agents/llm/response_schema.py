from pydantic import BaseModel, Field
from typing import Literal

# =========================================
# LITERAL VALUES FOR OUTPUT SCHEMAS
# =========================================

Tools = Literal[
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

StrengthNote = Literal[
    "very_strong",
    "strong",
    "moderate",
    "supporting",
    "benign_stand_alone",
    "benign_strong",
    "benign_supporting",
]

# =========================================
# OUTPUT SCHEMAS
# =========================================
class CheckTechnicalResult(BaseModel):
    passed: bool = Field(
        description="""Whether there are any technical error in the task output, including 
        tool call failures, missing data, API errors, malformed outputs, or status=error. 
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
        not a string"""
    )

    applied_strength: StrengthNote | None = Field(
        description=""""Strength level for the criterion if it applies. 
        Use None when the criterion does not apply."""
    )

    status: Literal["complete", "error"] = Field(
        description="Use 'complete' if the interpretation succeeded. Use 'error' only if the task could not be completed."
    )





# class ValidationResult(BaseModel):
