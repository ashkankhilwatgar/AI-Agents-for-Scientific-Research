from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, asdict
from .vep import annotate_variant
import sys
from urllib.parse import quote
from config import NCBI_API_KEY
from config import NCBI_EMAIL
import os
import requests
from metapub import PubMedFetcher, FindIt
from pathlib import Path
import time
import json
# from langchain_google_genai import ChatGoogleGenerativeAI
import re
import urllib.request
from agents.llm.llm import create_llm, invoke_llm
from config import MODELS
from pprint import pprint
import re
from langchain_core.messages import HumanMessage, SystemMessage




# =============================================================================
# System Prompts
# =============================================================================
ABSTRACT_CLASSIFICATION_SYSTEM_PROMPT = """
You are a clinical variant interpretation curator performing a high-sensitivity, abstract-level screen for papers that contain variant functional experiments.

CRITICAL SCOPE RULE

The unit being classified is the PAPER OR ABSTRACT AS A WHOLE.
You are NOT deciding whether the paper contains functional evidence for a particular query variant.
A target variant may be supplied elsewhere in the input for retrieval purposes. Ignore that target variant when assigning `is_functional`.
Do not compare the variants tested in the abstract with the query variant.
Return `is_functional = true` when the abstract reports a qualifying functional experiment for ANY genetic variant, mutation, allele, or mutant, even when:
- the query variant is not tested;
- the query variant is not mentioned;
- only other variants are tested;
- the specific variant identities are not given;
- the paper would not provide direct PS3 or BS3 evidence for the query variant.
Never return `is_functional = false` solely because the target or query variant is absent from the experiments.

GOAL

Decide only whether the abstract contains ANY experimental wet-lab functional evidence about the effect of one or more genetic variants, mutations, alleles, or mutants on:
- protein function or behavior;
- RNA function or processing; or
- a disease-relevant cellular pathway or functional output.
This is a paper-level retrieval screen. It is not the downstream variant-matching or PS3/BS3 application step.

OUTPUT

Return only:
is_functional = true or false
and a brief justification describing the experimental assay and outcome.
Do not discuss whether the query variant was tested unless necessary to clarify that this does not affect the paper-level classification.

SENSITIVITY REQUIREMENT

This screen is intentionally high-sensitivity.
When there is reasonable doubt, return `is_functional = true` so the paper can be reviewed downstream.
Default to true whenever the abstract contains both:
(A). A variant or mutant subject
and
(B). A wet-lab functional assay with a reported outcome.

CONDITION A: VARIANT OR MUTANT SUBJECT

Any of the following satisfies this condition:
- one or more specific variants, such as an HGVS name, rsID, nucleotide change, or amino-acid substitution;
- patient mutations or variants;
- disease-causing mutations;
- mutant alleles;
- an allelic series;
- mutant constructs;
- site-directed mutants;
- missense mutants;
- a variant panel;
- mutagenesis;
- engineered mutant proteins;
- CRISPR-introduced or knock-in variants;
- patient-derived samples whose experimental results are linked to mutations.
The tested variants do not need to match any query variant.

CONDITION B: WET-LAB FUNCTIONAL ASSAY AND OUTCOME

The abstract must describe an experimental functional measurement and report an outcome for one or more variants or mutants.
Qualifying outcomes include:
- reduced, abolished, or impaired function;
- increased activity or gain of function;
- altered or disrupted function;
- restored or rescued function;
- abnormal or normal localization;
- defective or normal trafficking;
- increased or decreased stability;
- degradation or altered half-life;
- defective or normal splicing;
- nonsense-mediated decay;
- altered binding;
- abnormal signaling;
- no difference from wild type;
- another experimentally observed effect on protein, RNA, cellular, or pathway function.

QUALIFYING FUNCTIONAL EXPERIMENTS

1. Protein or biochemical experiments
- enzymatic activity or kinetics;
- catalytic function;
- substrate turnover;
- protein binding or interaction;
- complex formation;
- protein folding;
- protein stability;
- degradation or half-life;
- localization;
- trafficking;
- secretion;
- receptor activity;
- signaling output;
- channel activity;
- transport activity;
- experimentally measured post-translational processing.

2. Cell-based experiments
- reporter assays;
- pathway-activity assays;
- electrophysiology;
- transport or flux measurements;
- rescue or complementation experiments;
- mutant-versus-wild-type comparisons;
- disease-relevant cellular phenotypes linked to a mutant.

3. RNA-level experiments
- RT-PCR or patient RNA experiments showing altered splicing;
- minigene splicing assays;
- experimentally demonstrated nonsense-mediated decay;
- mRNA stability measurements;
- experimentally measured RNA processing or translation effects.

4. Variant model systems
- knock-in models;
- CRISPR-engineered variants;
- engineered variant organisms or cells;
- variant-linked functional or disease-relevant phenotypes.

5. Patient-derived experiments
- enzyme activity;
- electrophysiology;
- signaling or pathway output;
- splicing defects;
- other functional measurements in patient cells or tissues when linked to mutations.

STRONG TRUE-CLASSIFICATION RULES

Return `is_functional = true` when any of the following patterns is present:
- mutation, variant, mutant, or allele language together with an experimental assay involving activity, localization, trafficking, stability, binding, signaling, splicing, RT-PCR, minigene, NMD, electrophysiology, rescue, or another functional measurement;
- the abstract states that mutations impair, reduce, increase, alter, disrupt, restore, or preserve function;
- mutant proteins are experimentally expressed and their cellular behavior is measured;
- some tested mutants show an abnormal result while other tested mutants show normal or different results.
RETURN FALSE ONLY WHEN CLEARLY NON-FUNCTIONAL
Return `is_functional = false` only when the abstract clearly lacks variant-level wet-lab functional testing, such as:
- purely computational or in-silico predictions;
- genetic association or segregation analysis without a functional experiment;
- case reports or patient phenotypes without a functional readout;
- gene knockout or ordinary gene overexpression experiments that do not test variants or mutant constructs;
- expression or omics profiling alone without a variant-linked functional consequence;
- a review, commentary, or methods proposal without reported variant functional results.

IMPORTANT DISTINCTION

The following two questions are different:
1. Does this paper contain any variant functional experiments?
2. Does this paper contain functional evidence for the query variant?

You are answering only Question 1.

EXAMPLE 1

The query variant is T615M. The abstract experimentally tests L32R, V49F, C53R, and other mutants and reports defective protein trafficking.

Output:
is_functional = true

Justification:
The abstract reports wet-lab trafficking experiments for multiple mutant proteins. The absence of T615M does not affect this paper-level classification.

EXAMPLE 2

The abstract mentions T615M only in patients and provides computational pathogenicity predictions, with no wet-lab assay.

Output:
is_functional = false

Justification:
The abstract does not report an experimental functional measurement.

EXAMPLE 3

The abstract experimentally tests ten mutants and finds that eight have impaired activity while two behave like wild type.

Output:
is_functional = true

Justification:
Both damaging and normal experimental outcomes count as variant functional evidence.

FINAL DECISION RULE

Before answering, ask:
1. Does the abstract mention or experimentally create any variant, mutation, allele, or mutant?
2. Does it report any wet-lab functional assay and an outcome for at least one of them?

If both answers are yes, return `is_functional = true`.
Do not check whether the tested variant matches the query variant.
Never return false merely because the query variant was not tested.
"""


PDF_EXTRACTION_SYSTEM_PROMPT = r"""
You are a clinical variant functional-evidence extractor for ACMG/AMP guidelines PS3/BS3 criteria.

INPUTS
- TARGET_VARIANT: gene + identifiers (any of rsID, HGVSg, chr_pos_ref_alt,
  HGVSc, HGVSp, aliases).
- PAPER: a full PDF (may include many variants).

GOAL
- Find all plausible variant-level functional experiments that might correspond to the TARGET_VARIANT. Read all PDF (text, tables, figure captions, and figure panels/embedded labels)
- Be SENSITIVE: when in doubt, extract and clearly mark uncertainty.
- Do NOT hallucinate data.

OUTPUT
- Return ONLY valid JSON that matches the schema exactly.
- Use double quotes for all keys and strings.
- No commentary outside JSON.

────────────────────────────────────
1. VARIANT MATCHING (SOFT GATE)
────────────────────────────────────
Build an equivalents set for the TARGET_VARIANT (without inventing mappings):
- Same rsID
- Same genomic coordinates (exact chr:pos:ref:alt or HGVSg as given)
- Same cDNA change (c.notation; allow formatting variants)
- Same protein change (same ref AA, same position, same alt AA;
  allow 1-letter ↔ 3-letter and formatting variants)

Do NOT:
- Change genome build
- Renumber across transcripts unless the paper explicitly gives both
- Guess transcript IDs

Match tiers (you can stop when one is clearly satisfied):

1) STRICT MATCH → status = "matched"
   - Exact rsID, genomic, cDNA, or protein match from the equivalents set,
     in the correct gene.
   - match_type = "rsid" / "genomic" / "cdna" / "protein" / "multiple"
   - confidence:
     - "high": rsID or genomic
     - "medium": cDNA or protein + clear gene context
     - "low": identifier match but weak context

2) SINGLE VARIANT STUDY → status = "single_variant_study_matching"
   - Functional experiments in this gene clearly test ONE specific variant only.
   - No other specific variants appear in functional results.
   - confidence:
     - "medium" if gene and clinical context are clear
     - "low" if context is weaker
   - match_type = "single_variant_study"

3) HEURISTIC MATCH → status = "heuristic_matching"
   Use for plausible, non-strict matches in the same gene. Count applicable clues:

   Clues:
    - Same amino-acid substitution (same ref AA, position, alt AA) but written
    in words or non-standard notation (e.g. "R158W mutant", "R158→W").
    - Explicit numbering / isoform / precursor→mature mapping that links positions
    to the same amino acid change.
    - Different cDNA / protein numbering that the paper directly ties together
    (e.g. "c.472C>T (R158W)").
    - Shorthand label ("mut1", "A", etc.) that is expanded elsewhere to a notation
    matching the TARGET_VARIANT equivalents.
    - Table / figure / text cross-reference that explicitly equates two labels
    as the same variant.
    - Multiplex / saturation screen where the authors systematically test single
    substitutions and the tested set clearly includes the TARGET codon / position
    (e.g. "all single-amino-acid substitutions at residue 158").

    Never call heuristic_matching based only on:
    - Same exon / domain / region, "nearby" codon, or vague proximity.
    - Gene-level statements with no specific variant label.

   - match_type = "heuristic"
   - confidence: "low" if 1 clue; "medium" if ≥2 clues

4) NO PLAUSIBLE VARIANT → status = "variant_matching_unsuccessful"
   - Use ONLY when you find no specific variant in this gene that could
     reasonably be the TARGET_VARIANT.
   - In this case: experiments = [] and overall_evidence.evidence_level =
     "not_clear" and evidence_strength = "not_clear".

IMPORTANT SENSITIVITY RULE:
- If you see any specific variant in the SAME GENE that could plausibly be the
  TARGET_VARIANT, you SHOULD:
  - Assign "matched", "single_variant_study_matching", or "heuristic_matching"
    with appropriate (often low) confidence.
  - Extract its experiments.
  - Explain uncertainty in variant_match.notes and overall_evidence.basis.
- Only use "variant_matching_unsuccessful" when there is truly no plausible
  candidate.

────────────────────────────────────
2. EXPERIMENT EXTRACTION
────────────────────────────────────
Extract experiments ONLY for the variant(s) linked to the TARGET_VARIANT by
your chosen status (matched / single_variant_study_matching / heuristic_matching).

INCLUDE:
- Experiments where the specific variant label (e.g. "R158W", "mut1",
  "c.472C>T") has its own row, bar, lane, or result.
- Variant-level results in tables, figures, or text.

EXCLUDE:
- Purely in silico predictions.
- Case reports or association studies with no functional assay.
- Results where variants are pooled and no individual variant result is given.

For each experiment, record:
- What the assay is (assay)
- The system used (system)
- How the variant material was obtained (variant_material)
- The measured endpoint (readout)
- The explicit comparator (normal_comparator: WT/healthy/threshold)
- The functional direction and any numbers (result.direction and
  result.effect_size_and_stats)
- Controls and validation details (controls_and_validation)
- Authors' explicit conclusion about the variant (authors_conclusion)
- Where it appears (where_in_paper)
- Limitations stated in the paper (caveats)
- Exact variant label in the paper (paper_variant_label)
- How strongly you link that label to the TARGET_VARIANT
  (variant_link_confidence).

If you find NO functional assay on the matched variant:
- experiments = []
- overall_evidence.evidence_level = "not_clear"
- overall_evidence.evidence_strength = "not_clear"
- State this in overall_evidence.basis.

────────────────────────────────────
3. PS3 / BS3 / not_clear
────────────────────────────────────
Definitions:
- PS3: Variant shows a functionally abnormal result (for example vs. a normal comparator),
consistent with a damaging effect and disease mechanism.
- BS3: Variant shows functionally normal result (for example vs. a normal comparator).
- not_clear: unclear direction, conflicting or insufficient information.

Strength (very_strong / strong / moderate / supporting / not_clear):
- supporting: comparator present + basic controls described (WT ± positive/null) but limited validation
- moderate: well-established assay with clear controls/replication and/or multiple validation controls described
- strong/very_strong: the paper provides rigorous clinical validation/calibration supporting high confidence
  (e.g., multiple known benign/pathogenic controls with clear thresholds or explicit calibration).

If evidence_level = "not_clear":
- evidence_strength MUST be "not_clear".

────────────────────────────────────
4. SUMMARY
────────────────────────────────────
In summary:
- Be generous in extraction when the variant is plausibly the TARGET_VARIANT.
- Use status, confidence, variant_link_confidence, and notes to mark how sure
  you are.
- Never invent experiments or numbers.
- Output must be valid JSON according to the schema, with no extra keys.
"""

# JSON Schema for structured PDF extraction output
VARIANT_FUNCTIONAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "target_variant_input",
        "variant_match",
        "experiments",
        "overall_evidence",
        "summary"
    ],
    "properties": {
        "target_variant_input": {
            "type": "string",
            "description": "Raw TARGET_VARIANT input string"
        },
        "variant_match": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "status",
                "confidence",
                "match_type",
                "matched_strings_in_paper",
                "equivalents_used",
                "where_in_paper",
                "notes"
            ],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": [
                        "matched",
                        "single_variant_study_matching",
                        "heuristic_matching",
                        "variant_matching_unsuccessful"
                    ],
                    "description": "Overall matching outcome for the TARGET_VARIANT"
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low", "not_clear"],
                    "description": "Overall confidence that the matched variant(s) correspond to the TARGET_VARIANT"
                },
                "match_type": {
                    "type": "string",
                    "enum": [
                        "rsid",
                        "genomic",
                        "cdna",
                        "protein",
                        "multiple",
                        "single_variant_study",
                        "heuristic",
                        "not_clear"
                    ],
                    "description": "Primary identifier or pattern used to link the paper variant(s) to the TARGET_VARIANT"
                },
                "matched_strings_in_paper": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exact matching strings as they appear in the paper"
                },
                "equivalents_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of equivalent forms of TARGET_VARIANT used in the search"
                },
                "where_in_paper": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Locations of the matched strings"
                },
                "notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Short notes explaining matching rationale and any ambiguity"
                }
            }
        },
        "experiments": {
            "type": "array",
            "description": "Functional experiments for the variant(s) linked to the TARGET_VARIANT",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "assay",
                    "system",
                    "variant_material",
                    "readout",
                    "normal_comparator",
                    "result",
                    "controls_and_validation",
                    "authors_conclusion",
                    "where_in_paper",
                    "caveats",
                    "paper_variant_label",
                    "variant_link_confidence"
                ],
                "properties": {
                    "assay": {
                        "type": ["string", "null"],
                        "description": "Assay type"
                    },
                    "system": {
                        "type": ["string", "null"],
                        "description": "Experimental system"
                    },
                    "variant_material": {
                        "type": ["string", "null"],
                        "description": "Source of the variant material"
                    },
                    "readout": {
                        "type": ["string", "null"],
                        "description": "Measured endpoint with units"
                    },
                    "normal_comparator": {
                        "type": ["string", "null"],
                        "description": "Explicit comparator defining normal function"
                    },
                    "result": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["direction", "effect_size_and_stats"],
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": [
                                    "functionally_abnormal",
                                    "functionally_normal",
                                    "intermediate",
                                    "mixed",
                                    "unclear"
                                ],
                                "description": "Functional impact relative to the comparator"
                            },
                            "effect_size_and_stats": {
                                "type": ["string", "null"],
                                "description": "Quantitative details as reported"
                            }
                        }
                    },
                    "controls_and_validation": {
                        "type": ["string", "null"],
                        "description": "Information on assay controls and validation"
                    },
                    "authors_conclusion": {
                        "type": ["string", "null"],
                        "description": "Authors' interpretation of the variant effect"
                    },
                    "where_in_paper": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific locations of this experiment"
                    },
                    "caveats": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Limitations mentioned in the paper"
                    },
                    "paper_variant_label": {
                        "type": ["string", "null"],
                        "description": "Exact variant label used in the paper"
                    },
                    "variant_link_confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence that paper_variant_label corresponds to TARGET_VARIANT"
                    }
                }
            }
        },
        "overall_evidence": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "evidence_level",
                "evidence_strength",
                "odds_path",
                "validation_basis",
                "basis"
            ],
            "properties": {
                "evidence_level": {
                    "type": "string",
                    "enum": ["PS3", "BS3", "not_clear"],
                    "description": "Overall functional evidence classification"
                },
                "evidence_strength": {
                    "type": "string",
                    "enum": ["very_strong", "strong", "moderate", "supporting", "not_clear"],
                    "description": "Strength of the functional evidence"
                },
                "odds_path": {
                    "type": ["number", "null"],
                    "description": "OddsPath value if explicitly reported"
                },
                "validation_basis": {
                    "type": ["string", "null"],
                    "description": "Justification for the chosen evidence_strength"
                },
                "basis": {
                    "type": "string",
                    "description": "Short rationale summarizing the evidence"
                }
            }
        },
        "summary": {
            "type": "string",
            "description": "2–5 sentence narrative of the PS3/BS3 call"
        }
    }
}


# # =============================================================================
# # LLMs (This is temporary). We have to rewrite the entire llm calling logic later
# # =============================================================================

# # For now let's use a web api for this function. I will change it after rewrite the llm wrapper logic
# def get_llm() -> Any:
#     """
#     Initialize and return the appropriate LLM based on LLM_PROVIDER config.
#     """
#     return ChatGoogleGenerativeAI(
#         model = "gemini-2.5-flash",
#         temperature = 0,
#        #  api_key = your_google_api_key_here    When you guys are running this file, uncomment this line and replace your_google_api_key_here with the google genai api key in the shared google doc
#        )

# # Initialize LLM on module import
# LLM = get_llm()


# =============================================================================
# Config
# =============================================================================
# API endpoints
LITVAR2_API_BASE = "https://www.ncbi.nlm.nih.gov/research/litvar2-api"
ENTREZ_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# =============================================================================
# DATA CLASSES
# =============================================================================
@dataclass
class VariantInfo:
    """Store variant coordinate and annotation information."""
    # chrom: str
    # pos: int
    # ref: str
    # alt: str
    name: str
    rsid: Optional[str] = None
    hgvsc: Optional[str] = None
    hgvsp: Optional[str] = None
    gene_symbol: Optional[str] = None
    ensembl_transcript: Optional[str] = None
    mane_transcript: Optional[str] = None

    # def search_strings(self) -> List[str]:
    #     """
    #     Return a deduplicated list of variant IDs to search LitVar2.

    #     Uses:
    #     - a simple genomic string: CHR:POS REF>ALT
    #     - rsid, hgvsc, hgvsp
    #     - gene_symbol + hgvsc / hgvsp combos when available
    #     """
    #     genomic_str = f"{self.chrom}:{self.pos}{self.ref}>{self.alt}"

    #     candidates = [
    #         genomic_str,
    #         self.rsid,
    #         self.hgvsc,
    #         self.hgvsp,
    #     ]
    #     if self.gene_symbol and self.hgvsp:
    #         candidates.append(f"{self.gene_symbol} {self.hgvsp}")
    #     if self.gene_symbol and self.hgvsc:
    #         candidates.append(f"{self.gene_symbol} {self.hgvsc}")
    #     return sorted({c for c in candidates if c})


@dataclass
class CandidatePaper:
    """Store basic paper information from LitVar2."""
    pmid: str
    title: str
    abstract: str
    source: str = "litvar2"
    why_relevant: str = "LitVar2 variant mention"


@dataclass
class FunctionalPaper:
    """Store paper with confirmed functional experiments."""
    pmid: str
    title: str
    justification: str
    pdf_path: Optional[str] = None  # path to downloaded PDF, if available


@dataclass
class FunctionalExperiment:
    """Store detailed functional experiment information."""
    pmid: str
    assay_type: str
    system: str
    readout: str
    effect_direction: str
    magnitude_stats: str
    controls_validity: str
    authors_conclusion: str
    evaluation: str





# =============================================================================
# VEP tools
# =============================================================================
def enrich_with_vep(vi: VariantInfo, vep_info: dict) -> None:
    """Update VariantInfo with VEP annotations if present."""
    if not vep_info:
        return 

    if vep_info.get("rsid") and not vi.rsid:
        vi.rsid = vep_info["rsid"]

    if vep_info.get("gene_symbol") and not vi.gene_symbol:
        vi.gene_symbol = vep_info["gene_symbol"]

    if vep_info.get("hgvsc"):
        vi.hgvsc = vep_info["hgvsc"]

    if vep_info.get("hgvsp"):
        vi.hgvsp = vep_info["hgvsp"]

    if vep_info.get("ensembl_transcript"):
        vi.ensembl_transcript = vep_info["ensembl_transcript"]

    if vep_info.get("mane_transcript"):
        vi.mane_transcript = vep_info["mane_transcript"]

# =============================================================================
# Utils
# =============================================================================
def build_variant_label(vi: VariantInfo) -> str:
    """
    Build a simple, LLM-friendly "variant of interest" string.
    """
    # print("build_variant_label ", "vi type", type(vi))

    # print("build variant label: ", vi.name)
    return (
        f"{vi.name}, "
        f"HGVSp:{vi.hgvsp}, HGVSc:{vi.hgvsc}, rsID:{vi.rsid}, symbol:{vi.gene_symbol}"
    )

# def restore_hgvs_notation(variant: str) -> str:
#     """
#     Convert a filename-safe variant name back to HGVS notation.

#     Example:
#         NM_000020_3_c_1445C_T -> NM_000020.3:c.1445C>T
#     """
#     pattern = re.compile(
#         r"^(?P<accession>[A-Z]+_\d+)_"  # NM_000020_
#         r"(?P<version>\d+)_"            # 3_
#         r"(?P<sequence_type>[cgnmpr])_" # c_
#         r"(?P<position>.+?)_"           # 1445C_
#         r"(?P<alternate>[A-Za-z*]+)$"   # T
#     )

#     match = pattern.fullmatch(variant.strip())

#     if match is None:
#         raise ValueError(f"Unsupported variant format: {variant!r}")

#     return (
#         f"{match.group('accession')}.{match.group('version')}:"
#         f"{match.group('sequence_type')}."
#         f"{match.group('position')}>{match.group('alternate')}"
#     )

# # =============================================================================
# # Literature Query Functions 
# # =============================================================================

# def query_pubtator(vi: VariantInfo) -> set[str]:
#     """
#     Query pubTator using hvgs variant name.
#     Returns a set of all unique PMIDs found.
#     """
#     endpoint = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
#     pmids = set()
#     page = 1

#     print("+++++++++++++++++++++++++++++++++++++++")
#     print("varinat:", vi.name)
#     print("+++++++++++++++++++++++++++++++++++++++")

#     try:
#         while True:
#             response = requests.get(
#                 endpoint,
#                 params={
#                     "text": restore_hgvs_notation(vi.name),
#                     "page": 1
#                 },
#                 timeout=30
#             )

#             if not response.ok:
#                 return set()

#             data = response.json()
#             results = data.get("results")

#             if not isinstance(results, list):
#                 return set()
            
#             for result in results:
#                 pmid = result.get("PMID") or result.get("PMID")
#                 if pmid is not None:
#                     pmids.add(str(pmid))

            
#             total_pages = int(data.get("total_pages", 1))
#             if page >= total_pages:
#                 break
        
#         return pmids
            
#     except Exception as e:
#         return set()
    
# def query_pubmed_Esearch(vi: VariantInfo) -> set:
#     """
#     Query pubTator using hvgs variant name.
#     Returns a set of all unique PMIDs found.
#     """
#     endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#     pmids = set()

#     try:
#         resp = requests.get(
#             endpoint,
#             params={
#                 "db": "pubmed",
#                 "term": restore_hgvs_notation(vi.name),
#                 "retmode": "json",
#                 "retmax": 10_000
#             }
#         )

#         data = resp.json()

#         if isinstance(data, dict):
#             idlist = data.get("esearchresult", {}).get("idlist", [])
#             if idlist and isinstance(idlist, list):
#                 for pmid in idlist:
#                     pmids.add(str(pmid))
        
#         return pmids
    
#     except Exception as e:
#         return set()

def query_litvar2(vi: VariantInfo) -> Set[str]:
    """
    Query LitVar2 using rsid only.
    Returns a set of all unique PMIDs found.
    
    Raises SystemExit if rsid is not available.
    """
    # Validate rsid exists. LitVar2 can only be queried by rsID; when a variant
    # has none (common for indels/frameshifts), there is simply no functional
    # literature to retrieve. Return an empty set so PS3/BS3 evaluate as
    # "no experiments found -> not applied" (the intended convention). Do NOT
    # sys.exit() here: this runs inside a LangGraph worker thread, and SystemExit
    # is not caught by `except Exception`, so it silently kills the whole
    # (batch) process instead of failing just this one criterion.
    
    rsid = vi.rsid
    if not rsid or rsid.lower() in ('none', 'na', 'null', 'n/a', ''):
        print(f"No RSID available for the variant {vi.name}")
        return set()
    
    print(f"{"-"*100}")
    print("RSID: ")
    print(rsid)
    print(f"{"-"*100}")

    pmids = query_litvar2_publications(rsid)
    return pmids

FETCHER = PubMedFetcher()

def query_litvar2_publications(variant_id: str) -> Set[str]:
    """
    Query LitVar2 API for publications mentioning a variant.
    Returns set of PMIDs.

    Endpoint:
    https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/get/{variantId}/publications
    """
    try:
        encoded_variant = quote(variant_id, safe='')
        print("litvar 2 encoded variant that is send to the server: ")
        print(encoded_variant)

        url = f"{LITVAR2_API_BASE}/variant/get/litvar@{encoded_variant}%23%23/publications"
        print(f"   Querying LitVar2: {url}...")

        resp = requests.get(url, timeout=30)

        if not resp.ok:
            print(f"   Warning: LitVar2 returned status {resp.status_code} for '{variant_id}'")
            return set()

        data = resp.json()

        # print(f"{"-"*100}")
        # print("litvar2 data returned: ")
        # pprint(data)
        # print(f"{"-"*100}")

        pmids = set()

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    pmid = item.get('pmid') or item.get('PMID')
                    if pmid:
                        pmids.add(str(pmid))
                elif isinstance(item, (str, int)):
                    pmids.add(str(item))
        elif isinstance(data, dict):
            for key in ['pmids', 'PMIDs', 'publications', 'results', 'data']:
                if key in data:
                    items = data[key]
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                pmid = item.get('pmid') or item.get('PMID')
                                if pmid:
                                    pmids.add(str(pmid))
                            else:
                                pmids.add(str(item))
                    break

        if pmids:
            # print(f"   Found {len(pmids)} publications for '{variant_id}'")
            pass
        else:
            # print(f"   No publications found for '{variant_id}'")
            pass

        return pmids

    except Exception as e:
        # print(f"   Warning: LitVar2 query failed for '{variant_id}': {e}")
        return set()

def pubmed_fetch_details(pmids: List[str]) -> Dict[str, CandidatePaper]:
    """
    Fetch full details (title, abstract) for a list of PMIDs using metapub.

    Uses:
        from metapub import PubMedFetcher
        article = FETCHER.article_by_pmid(pmid)
    """
    if not pmids:
        return {}

    result: Dict[str, CandidatePaper] = {}

    # print(f"   Fetching details for {len(pmids)} papers from PubMed via metapub...")

    for pmid in pmids:
        pmid_str = str(pmid)
        try:
            article = FETCHER.article_by_pmid(pmid_str)
        except Exception as e:
            # print(f"   Warning: metapub failed for PMID {pmid_str}: {e}")
            continue

        if article is None:
            # print(f"   Warning: no article object returned for PMID {pmid_str}")
            continue

        title = article.title or ""
        abstract = article.abstract or ""

        result[pmid_str] = CandidatePaper(
            pmid=pmid_str,
            title=title,
            abstract=abstract,
            source="litvar2",
            why_relevant="LitVar2 variant mention",
        )

        # Light throttling to be polite
        time.sleep(0.1)

    return result

def build_candidate_list(pmids: Set[str]) -> List[CandidatePaper]:
    """
    Fetch paper details from PubMed for all PMIDs from LitVar2.
    """
    if not pmids:
        return []

    pmid_list = sorted(list(pmids))
    papers_dict = pubmed_fetch_details(pmid_list)

    return list(papers_dict.values())

def check_open_access_from_doi(doi: str) -> str:
    """
    Check if a DOI is open access using Unpaywall API.
    
    Parameters
    ----------
    doi : str
        The DOI to check
        
    Returns
    -------
    str
        URL to open access PDF if available, empty string otherwise
    """
    if not doi:
        return ""

    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": NCBI_EMAIL}

    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return ""

        data = r.json()
        if data.get("is_oa"):
            # Try to get the best OA location
            best_oa = data.get("best_oa_location", {})
            if best_oa:
                pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                if pdf_url:
                    return pdf_url
            return data.get("doi_url", "")
        return ""

    except Exception:
        return ""

def fetch_pdf_url(pmid: str) -> str:
    """
    Fetch PDF URL for a PMID using multiple methods.
    
    Tries:
    1. metapub FindIt for direct PDF discovery
    2. Unpaywall API via DOI for open access
    
    Parameters
    ----------
    pmid : str
        PubMed ID
        
    Returns
    -------
    str
        URL to PDF if found, empty string otherwise
    """
    try:
        # Try metapub FindIt first
        finder = FindIt(pmid)
        if finder.url:
            return finder.url
        
        # Fallback: try Unpaywall via DOI
        article = FETCHER.article_by_pmid(pmid)
        if article and hasattr(article, "doi") and article.doi:
            url = check_open_access_from_doi(article.doi)
            if url:
                return url
        
        return ""
    except Exception as e:
        # print(f"   Warning: Failed to find PDF URL for PMID {pmid}: {e}")
        return ""

def download_pdf(pmid: str, pdf_dir: str, url: Optional[str] = None) -> Optional[str]:
    """
    Download PDF for a PMID to specified directory.
    
    Parameters
    ----------
    pmid : str
        PubMed ID
    pdf_dir : str
        Directory to save PDFs
    url : str, optional
        Pre-fetched PDF URL. If None, will attempt to discover URL.
        
    Returns
    -------
    str or None
        Path to downloaded PDF if successful, None otherwise
    """
    pdf_path = Path(pdf_dir) / f"{pmid}.pdf"
    
    # Check if already exists
    if pdf_path.exists():
        # print(f"   [→] PDF already exists for PMID {pmid}")
        return str(pdf_path)
    
    # Get URL if not provided
    if url is None:
        url = fetch_pdf_url(pmid)
    
    if not url:
        # print(f"   [✗] No PDF URL found for PMID {pmid}")
        return None
    
    try:
        # Ensure directory exists
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download with headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(pdf_path, 'wb') as f:
                f.write(response.read())
        
        # print(f"   [✓] Downloaded PDF for PMID {pmid}")
        return str(pdf_path)
        
    except Exception as e:
        # print(f"   [✗] Failed to download PDF for PMID {pmid}: {e}")
        return None


def download_pdfs_for_papers(
    pmids: List[str],
    pdf_dir: str,
    max_downloads: Optional[int] = None,
) -> Dict[str, str]:
    """
    Download PDFs for multiple PMIDs.
    
    Parameters
    ----------
    pmids : list of str
        List of PubMed IDs
    pdf_dir : str
        Directory to save PDFs
    max_downloads : int, optional
        Maximum number of PDFs to download. If None, download all.
        
    Returns
    -------
    dict
        Mapping from PMID to PDF path for successful downloads
    """
    downloaded = {}
    
    for i, pmid in enumerate(pmids):
        if max_downloads is not None and i >= max_downloads:
            break
            
        pdf_path = download_pdf(pmid, pdf_dir)
        if pdf_path:
            downloaded[pmid] = pdf_path
        
        # Rate limiting
        time.sleep(0.5)
    
    return downloaded



# =============================================================================
# Filtering 
# =============================================================================
def llm_filter_functional_papers(
    candidate_papers: List[CandidatePaper],
    variant_label: str,
) -> List[FunctionalPaper]:
    """
    Use an LLM to decide which papers contain experimental functional data.
    
    Uses high-sensitivity screening to minimize false negatives.
    Papers passing this filter should be reviewed with full-text extraction.
    """
    functional: List[FunctionalPaper] = []

    # print(f"   Filtering {len(candidate_papers)} papers for functional evidence...")

    for i, p in enumerate(candidate_papers, 1):
        if i % 10 == 0:
            # print(f"   Processed {i}/{len(candidate_papers)} papers...")
            pass

        # Build user prompt with paper details
        user_prompt = f"""Analyze this paper for functional evidence:

PMID: {p.pmid}
Title: {p.title}
Abstract: {p.abstract}

Based on the system instructions, respond in JSON with keys:
- "is_functional": true/false
- "justification": short string (1-3 sentences explaining your decision).
- "pmid": {p.pmid}
"""

        try:
            # Use system prompt + user prompt structure
            from langchain_core.messages import SystemMessage, HumanMessage
            

            
            content = invoke_llm(
                model=MODELS["functional_evidence"]["model"],
                provider=MODELS["functional_evidence"]["provider"],
                human_messsage=user_prompt,
                system_message=ABSTRACT_CLASSIFICATION_SYSTEM_PROMPT
            )

            # # resp.content can be a string or a list of content parts
            # content = resp.content
            if isinstance(content, list):
                # LangChain sometimes returns a list of dicts with "text"
                content = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                )

            # Clean up potential markdown code blocks
            content = re.sub(r"```(?:json)?", "", content).strip()
            content = content.replace("```", "")
            
            parsed = json.loads(content)

            print(f"{"="*100}")
            print("functional_experiment result:")
            pprint(parsed)
            print(f"{"="*100}")

            if parsed.get("is_functional"):
                functional.append(
                    FunctionalPaper(
                        pmid=p.pmid,
                        title=p.title,
                        justification=parsed.get("justification", "").strip(),
                    )
                )
        except Exception as e:
            # print(f"   Warning: LLM filtering failed for PMID {p.pmid}: {e}")
            continue

    return functional

def _parse_pdf_extraction_response(
    pmid: str,
    content: str,
) -> List[FunctionalExperiment]:
    """
    Parse JSON response from PDF extraction and convert to FunctionalExperiment objects.
    
    Common helper for all providers.
    """
    # Clean up potential markdown code blocks
    content = re.sub(r"```(?:json)?", "", content).strip()
    content = content.replace("```", "")
    
    parsed = json.loads(content)
    
    experiments = []
    for exp in parsed.get("experiments", []):
        result = exp.get("result", {})
        
        # Map direction to evaluation
        direction = result.get("direction", "unclear")
        if direction == "functionally_abnormal":
            evaluation = "supports_pathogenic"
            effect_dir = "loss_of_function"
        elif direction == "functionally_normal":
            evaluation = "supports_benign"
            effect_dir = "no_effect_vs_wildtype"
        else:
            evaluation = "ambiguous"
            effect_dir = "ambiguous"
        
        experiments.append(
            FunctionalExperiment(
                pmid=pmid,
                assay_type=exp.get("assay", "") or "",
                system=exp.get("system", "") or "",
                readout=exp.get("readout", "") or "",
                effect_direction=effect_dir,
                magnitude_stats=result.get("effect_size_and_stats", "") or "",
                controls_validity=exp.get("controls_and_validation", "") or "",
                authors_conclusion=exp.get("authors_conclusion", "") or "",
                evaluation=evaluation,
            )
        )
    
    return experiments

def _extract_from_pdf(
    pmid: str,
    variant_label: str,
    title: str,
    pdf_path: str
) -> List[FunctionalExperiment]:
    """
    Extract experiments from full-text PDF using the comprehensive schema.
    
    Supports multiple extraction modes:
    - Agentic: Uses OCR, layout detection, and VLM tools (page-by-page)
    - Simple: Uses provider-specific PDF upload APIs
    
    Supports multiple LLM providers for simple mode:
    - OpenAI: Uses file upload with responses API
    - Anthropic/Claude: Uses base64-encoded PDF with messages API
    - Gemini: Uses file upload with generative AI API
    """
    try:
        # import os
        # import google.generativeai as genai
        
        # # Configure the API
        # genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        
        # Upload the PDF file
        # uploaded_file = genai.upload_file(pdf_path, mime_type="application/pdf")
        
        user_prompt = f"""TARGET_VARIANT: {variant_label}

Attached: 1 full-text PDF paper (PMID: {pmid}, Title: {title}).

Follow the system instructions to:
- Match the TARGET_VARIANT to variant labels in the paper,
- Extract all plausible variant-level functional experiments for that variant,
- Summarize PS3/BS3 evidence and strength.

Return ONLY valid JSON that matches the schema exactly.
Do NOT add any text outside the JSON object.
"""
        
        # Create the model and generate content
        # model = genai.GenerativeModel(
        #     model_name="gemini-2.5-flash",
        #     system_instruction=PDF_EXTRACTION_SYSTEM_PROMPT,
        # )
        
        # resp = model.generate_content(
        #     [uploaded_file, user_prompt],
        #     generation_config=genai.types.GenerationConfig(
        #         temperature=0,
        #         response_mime_type="application/json",
        #     ),
        # )

        # url = fetch_pdf_url(pmid=pmid)

        model = create_llm(
            provider=MODELS["functional_evidence"]["provider"],
            model=MODELS["functional_evidence"]["model"],
        )

        messages = [
            SystemMessage(content=PDF_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text","text": user_prompt},
                    {"type": "file","url": pdf_path, "mime_type": "application/pdf"},
                ]
            )
        ]

        resp = model.invoke(messages)

        content = resp.content

        return _parse_pdf_extraction_response(pmid, pdf_path)
        
    except Exception as e:
        print(f"   Warning: PDF extraction failed for PMID {pmid}: {e}")
        return []



# def _extract_from_pdf(
#     pmid: str,
#     variant_label: str,
#     pdf_path: str,
#     title: str,
# ) -> List[FunctionalExperiment]:
#     """
#     Extract experiments from full-text PDF using the comprehensive schema.
    
#     Supports multiple extraction modes:
#     - Agentic: Uses OCR, layout detection, and VLM tools (page-by-page)
#     - Simple: Uses provider-specific PDF upload APIs
    
#     Supports multiple LLM providers for simple mode:
#     - OpenAI: Uses file upload with responses API
#     - Anthropic/Claude: Uses base64-encoded PDF with messages API
#     - Gemini: Uses file upload with generative AI API
#     """
#     # Let's use the Gemini-based extraction for now. 
#     return _extract_from_pdf_gemini(pmid, variant_label, pdf_path, title)


def entrez_get(endpoint: str, params: Dict) -> requests.Response:
    """Make a request to NCBI Entrez API."""
    base_params = {"email": NCBI_EMAIL}
    if NCBI_API_KEY:
        base_params["api_key"] = NCBI_API_KEY
    base_params.update(params)

    url = f"{ENTREZ_BASE}/{endpoint}"
    resp = requests.get(url, params=base_params, timeout=30)
    resp.raise_for_status()
    return resp

def fetch_full_text_or_abstract(pmid: str) -> str:
    """
    Retrieve text for a PMID (PubMed XML -> stripped text).

    This gives abstract + some additional metadata. No PMC complexity.
    """
    try:
        resp = entrez_get("efetch.fcgi", {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml",
        })
        xml_text = resp.text
        text = re.sub(r"<.*?>", " ", xml_text)
        text = re.sub(r"\s+", " ", text)
        return text
    except Exception as e:
        # print(f"   Warning: Failed to fetch text for PMID {pmid}: {e}")
        return ""

def _extract_from_abstract(
    pmid: str,
    variant_label: str,
    title: str,
) -> List[FunctionalExperiment]:
    """Extract experiments from abstract text (fallback when no PDF)."""
    from langchain_core.messages import SystemMessage, HumanMessage
    
    full_text = fetch_full_text_or_abstract(pmid)
    
    # Simplified extraction prompt for abstract-only
    system_prompt = """You are helping evaluate ACMG criteria PS3 and BS3 for a genetic variant.

ACMG functional criteria:
- PS3: Well-established in vitro or in vivo functional studies supportive of a damaging
  effect on the gene or gene product.
- BS3: Well-established in vitro or in vivo functional studies show no damaging effect
  on protein function or splicing.

Task: Extract all experiments that directly test the functional impact of the target variant.

Return JSON with key "experiments" containing a list of objects with these keys:
- assay_type: type of assay (e.g. "enzyme activity", "minigene splicing")
- system: experimental system (e.g. "HEK293 cells", "patient fibroblasts")
- readout: what was measured
- effect_direction: one of ["strong_loss_of_function", "partial_loss_of_function",
   "gain_of_function", "dominant_negative", "no_effect_vs_wildtype", "ambiguous"]
- magnitude_stats: quantitative details (fold-changes, p-values)
- controls_validity: information on controls and replication
- authors_conclusion: what authors conclude about the variant
- evaluation: one of ["supports_pathogenic", "supports_benign", "ambiguous", "low_quality"]

If no relevant experiments found, return {"experiments": []}.
"""
    
    user_prompt = f"""Variant of interest: {variant_label}
Paper PMID: {pmid}
Title: {title}

Paper text:
---
{full_text[:25000]}
---

Extract functional experiments for this variant and return as JSON.
"""
    
    try:
        # messages = [
        #     SystemMessage(content=system_prompt),
        #     HumanMessage(content=user_prompt)
        # ]
        
        # resp = LLM.invoke(messages)
        
        # content = resp.content

        content = invoke_llm(
            model=MODELS["functional_evidence"]["model"],
            provider=MODELS["functional_evidence"]["provider"],
            system_message=system_prompt,
            human_messsage=user_prompt
        )


        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        
        # Clean up potential markdown
        content = re.sub(r"```(?:json)?", "", content).strip()
        content = content.replace("```", "")
        
        parsed = json.loads(content)
        
        exp_list = parsed.get("experiments", [])
        if not isinstance(exp_list, list):
            return []
        
        experiments = []
        for e in exp_list:
            experiments.append(
                FunctionalExperiment(
                    pmid=pmid,
                    assay_type=e.get("assay_type", ""),
                    system=e.get("system", ""),
                    readout=e.get("readout", ""),
                    effect_direction=e.get("effect_direction", ""),
                    magnitude_stats=e.get("magnitude_stats", ""),
                    controls_validity=e.get("controls_validity", ""),
                    authors_conclusion=e.get("authors_conclusion", ""),
                    evaluation=e.get("evaluation", ""),
                )
            )
        return experiments
        
    except Exception as e:
        # print(f"   Warning: Abstract extraction failed for PMID {pmid}: {e}")
        return []

def llm_extract_experiments(
    functional_papers: List[FunctionalPaper],
    variant_label: str,
) -> List[FunctionalExperiment]:
    """
    Extract experiment details using LLM.
    
    If pdf_dir is provided and PDFs exist, will use full-text PDF extraction.
    Otherwise falls back to abstract-based extraction.
    
    Parameters
    ----------
    functional_papers : list of FunctionalPaper
        Papers identified as containing functional evidence
    variant_label : str
        Variant identifier string for LLM context
    pdf_dir : str, optional
        Directory containing PDFs named {pmid}.pdf
        
    Returns
    -------
    list of FunctionalExperiment
        Extracted experiments
    """
    experiments: List[FunctionalExperiment] = []

    pdf_dir = Path("tools/functional_papers")

    # print(f"   Extracting experiments from {len(functional_papers)} functional papers...")

    for i, fp in enumerate(functional_papers, 1):
        # print(f"   Processing paper {i}/{len(functional_papers)}: PMID {fp.pmid}")
        
        # # # Check if PDF exists
        # pdf_path = None
        # if not pdf_dir.exists():
        #     pdf_dir.mkdir(parents=True, exist_ok=True)
            
        # candidate_pdf = Path(pdf_dir) / f"{fp.pmid}.pdf"
        # if candidate_pdf.exists():
        #     pdf_path = str(candidate_pdf)
        #     fp.pdf_path = pdf_path
        
        # # Try PDF-based extraction first if available
        # if pdf_path:
        #     extracted = _extract_from_pdf(fp.pmid, variant_label, fp.title, pdf_path)
        #     if extracted:
        #         experiments.extend(extracted)
        #         continue
            
        # Fallback to abstract-based extraction
        extracted = _extract_from_abstract(fp.pmid, variant_label, fp.title)
        experiments.extend(extracted)

    return experiments



def analyze_variant(
    variant: str
) -> Dict[str, Any]:
    """
    Run the full PS3/BS3 functional evidence pipeline for a single variant,
    starting from CHROM, POS, REF, ALT.

    Parameters
    ----------
    variant: str
        Variant name in HGVS c. notation 

    Returns
    -------
    dict
        Dictionary containing variant info, candidate papers, functional papers,
        experiments, and assessment results.
    """

    vi = VariantInfo(name=variant)
    # print("variant info: variant nmae")
    # print(vi.name)
    # print("variant info, vi type")
    # print(type(vi))

    vep_info: Optional[Dict[str, Any]] = None
    try:
        vep_info = annotate_variant(variant)

        print(f"{"-"*100}")
        print("VEP info: ")
        print(vep_info)
        print(f"{"-"*100}")

        # print("VEP annotation successful")
        # print("VEP info: ")
        # print(vep_info)

        if vep_info:
            # print("   VEP annotation obtained.")
            # print("")
            enrich_with_vep(vi, vep_info)
            # print("Enriching successful")
        else:
            # print("   VEP returned no annotation.")
            pass
    except Exception as e:
        # print(f"   Warning: VEP annotation failed: {e}")
        pass

    variant_label = build_variant_label(vi)
    # print(f"\n   Variant label for LLM prompts: {variant_label}")
    # print("   Identifiers to query in LitVar2:")

    # 2. Query LitVar2 for PMIDs
    # print("Step 2: Querying LitVar2 for publications...")
    print(f"{"-"*100}")
    print("vi: ")
    pprint(asdict(vi))
    print(f"{"-"*100}")

    pmids = query_litvar2(vi)

    print(f"{"-"*100}")
    print("pmids: ")
    print(pmids)
    print(f"{"-"*100}")

    # if not pmids:
    #     pmids = query_pubtator(vi)
    #     if not pmids:
    #         pmids = query_pubmed_Esearch(vi)
    # print(f"   Total unique PMIDs from LitVar2: {len(pmids)}")

    # 3. Fetch paper details from PubMed via metapub
    # print("\nStep 3: Fetching paper details from PubMed...")
    candidate_papers = build_candidate_list(pmids)
    # print(f"   Retrieved details for {len(candidate_papers)} papers")

    print(f"{"-"*100}")
    print("candidate_papers: ")
    pprint([asdict(paper) for paper in candidate_papers])
    print(f"{"-"*100}")

    # 4. Filter for functional papers (high-sensitivity screening)
    # print("\nStep 4: Filtering for functionally relevant papers...")
    functional_papers = llm_filter_functional_papers(candidate_papers, variant_label)
    print(f"{"-"*100}")
    print("functional_papers: ")
    pprint([asdict(paper) for paper in functional_papers])
    print(f"{"-"*100}")
    # print(f"   Identified {len(functional_papers)} functionally relevant papers")

    # # # 4b. Download PDFs for functional papers (if enabled)
    # downloaded_pdfs = {}
    # pdf_path = "tools/functional_papers"
    # # if download_pdfs and pdf_path and functional_papers:
    # # print("\nStep 4b: Downloading PDFs for functional papers...")
    # functional_pmids = [fp.pmid for fp in functional_papers]
    # downloaded_pdfs = download_pdfs_for_papers(
    #     functional_pmids,
    #     pdf_path,
    # )
    # # print(f"   Downloaded/found {len(downloaded_pdfs)} PDFs")
        
    #     # Update functional papers with PDF paths
    # for fp in functional_papers:
    #     if fp.pmid in downloaded_pdfs:
    #         fp.pdf_path = downloaded_pdfs[fp.pmid]

    # 5. Extract experiments 
    # print("\nStep 5: Extracting functional experiments...")
    experiments = llm_extract_experiments(
        functional_papers,
        variant_label,
    )

    print(f"{"=" * 100}")
    print("RESULT: ")
    pprint(experiments)
    print(f"{"=" * 100}")


    return {"experiments": [asdict(e) for e in experiments]}
