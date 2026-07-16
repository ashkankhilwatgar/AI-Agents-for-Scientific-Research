from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, asdict
from .vep import annotate_variant
import sys
import base64
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
import base64
from pydantic import BaseModel
from agents.llm.response_schema import FunctionalPaperFiltering, FunctionalExperiments




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
- the specific variant identities are not given; abstract reports a qualifying functional experiment for ANY genetic variant, mutation, allele, or mutant
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

PDF_EXTRACTION_SYSTEM_PROMPT = """
You are a clinical variant-interpretation curator extracting functional
experiments from a scientific paper.

Your goal is to return only functional experiments that test the
TARGET_VARIANT.

The paper was selected by an upstream high-sensitivity screening step.
Therefore:

- The paper may contain functional experiments involving the TARGET_VARIANT.
- The paper may contain functional experiments involving only other variants.
- The paper may mention the TARGET_VARIANT without experimentally testing it.
- The paper may contain no functional experiments at all.

Do not assume that an experiment is relevant merely because the paper discusses
the same gene or was selected by the upstream screening step.

Return only the structured output required by the supplied schema.

Follow the procedure below internally. Do not output your reasoning process.

────────────────────────────────────
STEP 0 — BUILD TARGET VARIANT LABELS
────────────────────────────────────

Create a set of labels that can validly identify the TARGET_VARIANT.

Use only information supplied in the TARGET_VARIANT input, including, when
available:

- Gene symbol
- rsID
- Genomic coordinate or HGVSg
- HGVSc
- HGVSp
- Protein substitution
- Explicitly supplied equivalent labels

You may recognize formatting-only equivalents, such as:

- R158W
- p.R158W
- p.Arg158Trp
- Arg158Trp
- R158→W

These may be treated as equivalent only when they describe the same:

- Reference amino acid
- Amino-acid position
- Alternate amino acid

You may normalize insignificant formatting differences involving:

- Spaces
- Parentheses
- Capitalization
- One-letter versus three-letter amino-acid notation
- Presence or absence of prefixes such as "p." or "c."

Do not invent biological mappings.

Do not:

- Guess a transcript
- Convert between transcripts unless the mapping is explicitly supplied
- Change genome builds
- Guess genomic coordinates
- Renumber protein positions
- Treat nearby variants as equivalent
- Treat variants in the same exon or protein domain as equivalent
- Treat the same amino-acid position with a different alternate amino acid as
  equivalent

The resulting label set is called TARGET_VARIANT_LABELS.

────────────────────────────────────
STEP 1 — IDENTIFY ALL FUNCTIONAL EXPERIMENTS
────────────────────────────────────

Read the full paper and identify every candidate functional experiment.

Search relevant sections including:

- Methods
- Results
- Tables
- Figures
- Figure legends
- Supplementary descriptions

A functional experiment must experimentally measure an effect on the gene
product or a biologically relevant pathway or cellular output.

Examples include:

- Protein expression or abundance
- Protein localization or trafficking
- Protein stability
- Ligand binding
- Enzyme activity
- Receptor activity
- Signaling activity
- Reporter assays
- RNA expression
- RNA splicing
- Cellular behavior
- Rescue or complementation assays
- Disease-relevant pathway measurements

Do not consider the following to be functional experiments:

- Purely in silico predictions
- Computational pathogenicity scores
- Population-frequency analysis
- Case reports without an experimental assay
- Association studies without functional testing
- General statements about the gene
- Predictions based only on protein structure
- Literature summaries of experiments performed in another paper

If the paper contains no functional experiments:

- Set experiments to an empty list.
- Return the complete structured-output object.

────────────────────────────────────
STEP 2 — PROCESS EACH FUNCTIONAL EXPERIMENT
────────────────────────────────────

Examine each functional experiment independently.

For the current experiment, determine:

1. What assay was performed?
2. Which specific variant or variants were tested?
3. What result belongs to each tested variant?
4. Does the experiment contain an individual result for a label in
   TARGET_VARIANT_LABELS?

Use variant information from:

- Main text
- Methods
- Tables
- Figure labels
- Figure legends
- Sample names
- Construct names
- Lane labels
- Bar labels
- Explicit shorthand definitions

A shorthand label such as "mut1" may be linked to the TARGET_VARIANT only when
the paper explicitly defines that shorthand as the target variant.

────────────────────────────────────
STEP 3 — KEEP OR DISCARD THE EXPERIMENT
────────────────────────────────────

KEEP the experiment only when it reports an individual functional result for
the TARGET_VARIANT.

An experiment may be kept when:

- The target variant has its own table row
- The target variant has its own figure bar
- The target variant has its own point or curve
- The target variant has its own experimental lane
- The target variant has its own construct or sample
- The text explicitly reports a result for the target variant
- A systematic variant screen reports an individually identifiable result for
  the exact target variant

DISCARD the experiment when:

- It tests only another variant
- It tests another variant in the same gene
- It tests a nearby variant
- It tests a different substitution at the same amino-acid position
- It discusses the target variant but does not experimentally test it
- It reports only a gene-level result
- It reports only a pooled result for several variants
- It is impossible to determine whether the result belongs to the target
  variant
- The target variant appears only in the introduction, patient description,
  discussion, or reference list
- The connection to the target variant would require an unsupported
  transcript, coordinate, or numbering conversion

The fact that a paper studies only one variant does not prove that the variant
is the TARGET_VARIANT. The experiment must still contain a valid
target-variant label match.

────────────────────────────────────
STEP 4 — HANDLE MULTI-VARIANT EXPERIMENTS
────────────────────────────────────

One assay may test several variants.

When an assay includes both the TARGET_VARIANT and other variants:

- Keep only the result belonging to the TARGET_VARIANT.
- Do not include results belonging only to other variants.
- Use other variants only as comparators when the paper explicitly uses them
  that way.

If several variants are pooled together and the paper does not provide an
individual result for the TARGET_VARIANT:

- Discard the experiment.

If the paper provides an individually identifiable target-variant result within
a larger multiplex or saturation screen:

- Keep the target-variant result.

────────────────────────────────────
STEP 5 — CREATE THE EXPERIMENT OBJECT
────────────────────────────────────

For every retained experiment, create one functional experiment object using
the supplied schema.

Populate the required fields using only information stated or directly shown
in the paper, including:

- assay_type
- system
- readout
- effect_direction
- effect_size_and_stats
- controls_and_validation
- authors_conclusion

Do not invent missing information.

When a field permits null and the paper does not provide the information, use
null.

Do not infer:

- A numerical effect size that was not reported
- Statistical significance that was not reported
- Valid controls that were not described
- An author conclusion stronger than the paper's actual conclusion
- Pathogenicity or benignity solely from your own interpretation of the assay

Create separate experiment objects when the paper uses meaningfully different:

- Assay types
- Biological systems
- Readouts
- Functional endpoints

Do not create duplicate experiment objects when the same result is described in
both the text and a figure.

────────────────────────────────────
STEP 6 — CONTINUE UNTIL ALL EXPERIMENTS ARE PROCESSED
────────────────────────────────────

Repeat Steps 2 through 5 for every functional experiment found in the paper.

For each experiment:

- Keep it when it individually tests the TARGET_VARIANT.
- Discard it otherwise.

Do not stop after finding the first matching experiment.

Do not stop after finding the first nonmatching experiment.

────────────────────────────────────
STEP 7 — FINAL OUTPUT
────────────────────────────────────

After processing all functional experiments:

- Return all retained target-variant experiment objects in experiments.
- If no target-variant experiments remain, return experiments as an empty list.

An empty experiment list is correct in either of these situations:

1. The paper contains no functional experiments.
2. The paper contains functional experiments, but none individually test the
   TARGET_VARIANT.

Return only the complete structured-output object required by the schema.
Do not return explanatory text outside the structured output.
"""

ABSTRACT_EXTRACTION_SYSTEM_PROMPT = """
You are helping to extract functional experiments for a specific genetic
variant from the abstract of a scientific paper.

Your task is to return only experiments that directly test the functional
impact of the TARGET_VARIANT.

The abstract may:

- contain experiments involving the TARGET_VARIANT;
- contain experiments involving only other variants;
- mention the TARGET_VARIANT without functionally testing it; or
- contain no functional experiments at all.

Do not assume that an experiment is relevant merely because it studies the
same gene or another variant in the same gene.

Follow the procedure below internally. Return only the structured output
required by the output schema.

────────────────────────────────────
STEP 0 — BUILD TARGET VARIANT LABELS
────────────────────────────────────

Using the TARGET_VARIANT supplied in the user message, identify the labels that
can validly refer to that variant.

You may recognize formatting-only equivalents, including:

- one-letter and three-letter amino-acid notation;
- presence or absence of prefixes such as "p." or "c.";
- differences in spacing, capitalization, parentheses, or arrow notation.

For example, these may represent the same protein variant:

- R158W
- p.R158W
- p.Arg158Trp
- Arg158Trp
- R158→W

Only treat protein labels as equivalent when they have the same:

- reference amino acid;
- amino-acid position; and
- alternate amino acid.

Do not:

- guess transcript mappings;
- convert between transcripts unless the abstract explicitly provides the
  mapping;
- change genome builds;
- invent genomic or cDNA coordinates;
- renumber protein positions;
- treat nearby variants as equivalent;
- treat variants in the same exon or domain as equivalent; or
- treat different substitutions at the same amino-acid position as equivalent.

The resulting set is called TARGET_VARIANT_LABELS.

────────────────────────────────────
STEP 1 — IDENTIFY CANDIDATE FUNCTIONAL EXPERIMENTS
────────────────────────────────────

Read the abstract and identify every candidate experiment that measures the
functional effect of a genetic variant or mutant.

Examples include:

- protein expression or abundance;
- protein localization or trafficking;
- protein stability or degradation;
- enzyme activity;
- ligand binding or protein interaction;
- receptor or signaling activity;
- reporter assays;
- electrophysiology;
- transport or channel activity;
- RNA splicing;
- RT-PCR or minigene assays;
- nonsense-mediated decay;
- RNA stability;
- rescue or complementation assays;
- disease-relevant cellular or pathway measurements.

Do not treat the following as functional experiments:

- purely computational or in-silico predictions;
- pathogenicity prediction scores;
- population-frequency analysis;
- genetic association or segregation analysis without a functional assay;
- case reports without experimental functional measurements;
- patient phenotype descriptions alone;
- structural predictions without experimental validation;
- ordinary gene knockout or overexpression experiments that do not test a
  specific variant;
- reviews or summaries of experiments performed in other papers; or
- proposed experiments without reported results.

If the abstract contains no candidate functional experiments, return:

{"experiments": []}

────────────────────────────────────
STEP 2 — EVALUATE EACH EXPERIMENT
────────────────────────────────────

Process every candidate functional experiment independently.

For each experiment, determine:

1. What assay was performed?
2. Which variant or variants were tested?
3. What functional result was reported?
4. Does the experiment report an individual result for a label in
   TARGET_VARIANT_LABELS?

Use only information explicitly available in the abstract.

A shorthand name such as "mutant 1" may be connected to the TARGET_VARIANT only
when the abstract explicitly defines that shorthand as the target variant.

Do not assume that an unnamed mutant is the TARGET_VARIANT.

────────────────────────────────────
STEP 3 — KEEP OR DISCARD EACH EXPERIMENT
────────────────────────────────────

KEEP an experiment only when the abstract directly links the functional assay
and its result to the TARGET_VARIANT.

Examples of experiments to keep include:

- the abstract explicitly reports the target variant's activity;
- the target variant is compared with wild type;
- the target variant has an individually described localization, expression,
  signaling, splicing, binding, or other functional result;
- the abstract reports an individually identifiable result for the target
  variant within a larger panel of variants.

DISCARD an experiment when:

- it tests only another variant;
- it tests another variant in the same gene;
- it tests a nearby variant;
- it tests a different substitution at the same amino-acid position;
- the target variant is mentioned but not experimentally tested;
- the result is reported only at the gene level;
- several variants are pooled and no individual result is reported for the
  target variant;
- the abstract does not state which variant produced the result;
- linking the experiment to the target would require an unsupported transcript,
  coordinate, or numbering conversion; or
- the target variant appears only in the background, patient description,
  discussion, or conclusion.

The fact that the paper studies only one variant does not prove that the
variant is the TARGET_VARIANT. Its label must still match one of
TARGET_VARIANT_LABELS.

────────────────────────────────────
STEP 4 — HANDLE MULTI-VARIANT EXPERIMENTS
────────────────────────────────────

An experiment may test several variants.

If the experiment includes the TARGET_VARIANT and other variants:

- retain the experiment only for the TARGET_VARIANT result;
- do not describe results belonging only to the other variants.

If the variants are pooled together and the abstract does not provide an
individual result for the TARGET_VARIANT:

- discard the experiment.

If the abstract says that a panel of mutants was tested but does not state that
the TARGET_VARIANT was included:

- do not assume that the target variant was tested;
- discard the experiment.

────────────────────────────────────
STEP 5 — CREATE EXPERIMENT OBJECTS
────────────────────────────────────

For every retained experiment, create one experiment object that follows the
output schema.

Populate fields such as:

- assay_type;
- system;
- readout;
- effect_direction;
- effect_size_and_stats;
- controls_and_validation; and
- authors_conclusion.

Use only information explicitly reported in the abstract.

Do not invent:

- assay details;
- biological systems;
- numerical measurements;
- statistical significance;
- controls;
- conclusions; or
- variant-to-experiment connections.

Only include an experiment object if it has real, non-empty content for at
least one of:

- assay_type;
- system;
- readout; or
- authors_conclusion.

Do not return placeholder objects or experiment objects in which all meaningful
fields are empty or null.

Do not create duplicate experiment objects when the same experiment is
described more than once in the abstract.

────────────────────────────────────
STEP 6 — PROCESS ALL EXPERIMENTS
────────────────────────────────────

Continue until every candidate functional experiment in the abstract has been
evaluated.

For each experiment:

- keep it if it directly tests the TARGET_VARIANT;
- discard it otherwise.

Do not stop after finding the first matching experiment.

────────────────────────────────────
STEP 7 — FINAL OUTPUT
────────────────────────────────────

Return all retained experiment objects in the experiments list.

If no relevant experiments remain, return an empty list

This includes all of the following situations:

- the abstract contains no functional experiments;
- the abstract contains functional experiments only for other variants;
- the target variant is mentioned but not functionally tested;
- the abstract does not provide enough information to connect an experiment to
  the target variant;

Remove any experiment that fails one or more of these checks.

Return only the output required by the schema. Do not include explanatory text
outside the structured output.
"""

# =============================================================================
# LLM WRAPPER
# =============================================================================

def call_functional_llm(
        user_prompt: str | list, 
        system_prompt: str, 
        output_schema: type[BaseModel]
) -> dict:
    llm = create_llm(
        provider=MODELS["functional_evidence"]["provider"],
        model=MODELS["functional_evidence"]["model"],
    )

    structured_llm = llm.with_structured_output(output_schema)

    messages = [
        SystemMessage(system_prompt),
        HumanMessage(user_prompt),
    ]

    resp = structured_llm.invoke(messages).model_dump()

    return resp
         

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
    
    print(f"{'-'*100}")
    print("RSID: ")
    print(rsid)
    print(f"{'-'*100}")

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

        # print(f"{'-'*100}")
        # print("litvar2 data returned: ")
        # pprint(data)
        # print(f"{'-'*100}")

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

def fetch_pdf_url(pmid: str) -> tuple[str, str]:
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
    tuple[str, str]
        (url, source) — url to PDF if found (empty string otherwise), and
        which method produced it ("findit", "unpaywall", or "none"). The
        source label matters for debugging: FindIt frequently returns a
        publisher "article page" URL that returns HTML (paywall/cookie
        wall) instead of the actual PDF binary, whereas Unpaywall only
        returns links it believes are genuinely open-access full text.
    """
    try:
        # Try metapub FindIt first
        finder = FindIt(pmid)
        if finder.url:
            return finder.url, "findit"

        # Fallback: try Unpaywall via DOI
        article = FETCHER.article_by_pmid(pmid)
        if article and hasattr(article, "doi") and article.doi:
            url = check_open_access_from_doi(article.doi)
            if url:
                return url, "unpaywall"

        return "", "none"
    except Exception as e:
        print(f"   [!] Warning: Failed to find PDF URL for PMID {pmid}: {e}")
        return "", "none"

def download_pdf(pmid: str, pdf_dir: str, url: Optional[str] = None) -> Optional[str]:
    """
    Download PDF for a PMID to specified directory.

    Validates that the downloaded content is actually a PDF (via
    Content-Type header AND the '%PDF-' magic-byte signature) before
    writing it to disk. Many publisher URLs discovered by metapub's
    FindIt return HTTP 200 with an HTML paywall/landing page instead of
    the real PDF binary when fetched without a browser session — without
    this check, that HTML gets silently saved as a ".pdf" file that
    later fails to open ("Invalid or corrupted PDF file").

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

    # Check if already exists AND is a valid PDF (don't trust a
    # previously-saved file blindly — earlier runs may have saved HTML).
    if pdf_path.exists():
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(5)
            if header == b'%PDF-':
                return str(pdf_path)
            else:
                print(f"   [!] PMID {pmid}: existing file is not a valid PDF "
                      f"(header={header!r}) — re-downloading")
                pdf_path.unlink()
        except OSError as e:
            print(f"   [!] PMID {pmid}: could not read existing file, re-downloading: {e}")

    # Get URL if not provided
    source = "provided"
    if url is None:
        url, source = fetch_pdf_url(pmid)

    if not url:
        print(f"   [x] PMID {pmid}: no PDF URL found (source={source})")
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
            content_type = response.headers.get("Content-Type", "")
            data = response.read()

        # Validate: reject anything that isn't actually a PDF, regardless
        # of what Content-Type claims (some servers mislabel HTML as
        # application/pdf, so check both the header AND the magic bytes).
        looks_like_pdf = "pdf" in content_type.lower() or data.startswith(b"%PDF-")
        if not looks_like_pdf or not data.startswith(b"%PDF-"):
            print(f"   [x] PMID {pmid}: download did not return a valid PDF "
                  f"(source={source}, url={url}, Content-Type={content_type!r}, "
                  f"first bytes={data[:20]!r}) — likely a paywall/landing page. "
                  f"Discarding.")
            return None

        with open(pdf_path, 'wb') as f:
            f.write(data)

        print(f"   [v] Downloaded valid PDF for PMID {pmid} (source={source})")
        return str(pdf_path)

    except Exception as e:
        print(f"   [x] Failed to download PDF for PMID {pmid} (source={source}, url={url}): {e}")
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

        print(f"DOWNLOADING FOR PMID: {pmid}")
        
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

            content = call_functional_llm(
                user_prompt=user_prompt, 
                system_prompt=ABSTRACT_CLASSIFICATION_SYSTEM_PROMPT,
                output_schema=FunctionalPaperFiltering
            )

            print(f"{'='*100}")
            print("functional_experiment result:")
            pprint(content)
            print(f"{'='*100}")

            if isinstance(content, dict):
                if content.get("is_functional"):
                    functional.append(
                        FunctionalPaper(
                            pmid=p.pmid,
                            title=p.title,
                            justification=content.get("justification", "").strip(),
                        )
                    )
        except Exception as e:
            print(f"   [!] Warning: LLM filtering failed for PMID {p.pmid}: {e!r}")
            print(f"       Raw LLM content (first 500 chars): {str(content)[:500]!r}")
            continue

    return functional

def _parse_pdf_extraction_response(
    pmid: str,
    content: dict,
) -> List[FunctionalExperiment]:
    """
    Parse JSON response from PDF extraction and convert to FunctionalExperiment objects.
    
    Common helper for all providers.
    """
    skipped_blank = 0

    experiments = []
    for exp in content.get("experiments", []):
        assay_type = exp.get("assay_type", "") or ""
        system = exp.get("system", "") or ""
        readout = exp.get("readout", "") or ""
        authors_conclusion = exp.get("authors_conclusion", "") or ""

        # Skip empty-shell entries: if the model produced an "experiment"
        # with no actual assay/system/readout/conclusion content, it isn't
        # real evidence and would just add noise downstream (e.g. an
        # experiment with evaluation="" that PlanRAG's STEP 1 grouping
        # can't classify as anything).
        if not any([assay_type.strip(), system.strip(), readout.strip(), authors_conclusion.strip()]):
            skipped_blank += 1
            continue

        experiments.append(
            FunctionalExperiment(
                pmid=pmid,
                assay_type=assay_type,
                system=system,
                readout=readout,
                effect_direction=exp.get("effect_direction", "unclear"),
                magnitude_stats=exp.get("effect_size_and_stats", "") or "",
                controls_validity=exp.get("controls_and_validation", "") or "",
                authors_conclusion=authors_conclusion,
            )
        )

    if skipped_blank:
        print(f"   [!] PMID {pmid}: skipped {skipped_blank} empty-shell experiment "
              f"entr{'y' if skipped_blank == 1 else 'ies'} from PDF extraction")
    
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
        user_prompt = f"""TARGET_VARIANT: {variant_label}

Attached: 1 full-text PDF paper (PMID: {pmid}, Title: {title}).

Follow the system instructions to:
- Match the TARGET_VARIANT to variant labels in the paper,
- Extract all plausible variant-level functional experiments for that variant,
- Summarize PS3/BS3 evidence and strength.

Make sure you follow the output schema
"""
        with open(pdf_path, "rb") as f:
            base64_string = base64.b64encode(f.read()).decode("utf-8")

        resp = call_functional_llm(
            user_prompt=[{"type": "text","text": user_prompt},
                    {"type": "file","base64": base64_string, "mime_type": "application/pdf"},],
            system_prompt=PDF_EXTRACTION_SYSTEM_PROMPT,
            output_schema=FunctionalExperiments
        )
        return _parse_pdf_extraction_response(pmid, resp)
    except Exception as e:
        print(f"   Warning: PDF extraction failed for PMID {pmid}: {e}")
        return []

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
    
    user_prompt = f"""TARGET VARIANT: {variant_label}
Paper PMID: {pmid}
Title: {title}

Paper text:
---
{full_text[:25000]}
---

Extract functional experiments for this variant and return as JSON.
"""
    try:
        resp = call_functional_llm(
            user_prompt=user_prompt,
            system_prompt=ABSTRACT_EXTRACTION_SYSTEM_PROMPT,
            output_schema=FunctionalExperiments
        )
        exp_list = resp.get("experiments", [])
        if not isinstance(exp_list, list):
            print(f"   [!] Warning: PMID {pmid} abstract extraction returned "
                  f"non-list 'experiments' field: {exp_list!r}")
            return []

        experiments = []
        skipped_blank = 0
        for e in exp_list:
            experiments.append(
                FunctionalExperiment(
                    pmid=pmid,
                    assay_type=e.get("assay_type", ""),
                    system=e.get("system", ""),
                    readout=e.get("readout", ""),
                    effect_direction=e.get("effect_direction", "unclear"),
                    magnitude_stats=e.get("effect_size_and_stats", ""),
                    controls_validity=e.get("controls_and_validation", ""),
                    authors_conclusion=e.get("authors_conclusion", ""),
                )
            )

        if skipped_blank:
            print(f"   [!] PMID {pmid}: skipped {skipped_blank} empty-shell experiment "
                  f"entr{'y' if skipped_blank == 1 else 'ies'} from abstract extraction")

        return experiments

    except Exception as e:
        print(f"   [!] Warning: Abstract extraction failed for PMID {pmid}: {e!r}")
        # print(f"       Raw LLM content (first 500 chars): {str(content)[:500]!r}")
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

    if not pdf_dir.exists():
        pdf_dir.mkdir(parents=True, exist_ok=True)

    for i, fp in enumerate(functional_papers, 1):
        # Check if a valid PDF already exists on disk for this paper.
        # fp.pdf_path is only populated here (by analyze_variant's download
        # step) or left as None if download failed / was never attempted.
        pdf_path = fp.pdf_path
        if pdf_path is None:
            candidate_pdf = pdf_dir / f"{fp.pmid}.pdf"
            if candidate_pdf.exists():
                pdf_path = str(candidate_pdf)
                fp.pdf_path = pdf_path

        # Try PDF-based extraction first if a real PDF is available.
        if pdf_path:
            extracted = _extract_from_pdf(fp.pmid, variant_label, fp.title, pdf_path)
            if extracted:
                experiments.extend(extracted)
                continue
            print(f"   [!] PMID {fp.pmid}: PDF-based extraction returned no "
                  f"experiments, falling back to abstract-based extraction.")

        # Fallback to abstract-based extraction
        print(f"{"=" * 100}")
        print(f"Extracting {fp.pmid} from abstract")
        print(f"{"=" * 100}")
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

        print(f"{'-'*100}")
        print("VEP info: ")
        print(vep_info)
        print(f"{'-'*100}")

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
    print(f"{'-'*100}")
    print("vi: ")
    pprint(asdict(vi))
    print(f"{'-'*100}")

    pmids = query_litvar2(vi)

    print(f"{'-'*100}")
    print("pmids: ")
    print(pmids)
    print(f"{'-'*100}")

    # if not pmids:
    #     pmids = query_pubtator(vi)
    #     if not pmids:
    #         pmids = query_pubmed_Esearch(vi)
    # print(f"   Total unique PMIDs from LitVar2: {len(pmids)}")

    # 3. Fetch paper details from PubMed via metapub
    # print("\nStep 3: Fetching paper details from PubMed...")
    candidate_papers = build_candidate_list(pmids)
    # print(f"   Retrieved details for {len(candidate_papers)} papers")

    print(f"{'-'*100}")
    print("candidate_papers: ")
    pprint([asdict(paper) for paper in candidate_papers])
    print(f"{'-'*100}")

    # 4. Filter for functional papers (high-sensitivity screening)
    # print("\nStep 4: Filtering for functionally relevant papers...")
    functional_papers = llm_filter_functional_papers(candidate_papers, variant_label)
    print(f"{'-'*100}")
    print("functional_papers: ")
    pprint([asdict(paper) for paper in functional_papers])
    print(f"{'-'*100}")
    # print(f"   Identified {len(functional_papers)} functionally relevant papers")

    # 4b. Download PDFs for functional papers (best-effort — download_pdf()
    # validates Content-Type + '%PDF-' magic bytes and returns None rather
    # than saving a paywall/landing-page HTML file, so a missing pdf_path
    # here is expected for papers with no open-access full text, not a bug.
    pdf_dir = "tools/functional_papers"
    functional_pmids = [fp.pmid for fp in functional_papers]
    downloaded_pdfs = download_pdfs_for_papers(
        functional_pmids,
        pdf_dir,
    )
    print(f"{'-'*100}")
    print(f"Downloaded/found {len(downloaded_pdfs)}/{len(functional_pmids)} valid PDFs")
    print(f"{'-'*100}")

    # Update functional papers with PDF paths
    for fp in functional_papers:
        if fp.pmid in downloaded_pdfs:
            fp.pdf_path = downloaded_pdfs[fp.pmid]

    # 5. Extract experiments
    # print("\nStep 5: Extracting functional experiments...")
    experiments = llm_extract_experiments(
        functional_papers,
        variant_label,
    )

    print(f"{'='*100}")
    print("RESULT: ")
    pprint(experiments)
    print(f"{'='*100}")


    return {"experiments": [asdict(e) for e in experiments]}



if __name__ == "__main__":
    # Example usage
    variant = "NM_001114753.3:c.1844C>T"  # Example variant
    result = analyze_variant(variant)
