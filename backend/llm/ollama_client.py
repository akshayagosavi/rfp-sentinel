"""
M8: generic LLM classifier — the single reusable function behind both
check_rfp_compliance (M9, verdicts: compliant/violation/unclear) and
retrieve_and_extract_evidence (M11, verdicts: pass/fail/partial/not_found).

Not compliance-specific or bid-specific — the caller supplies the verdict
labels and the instruction, this module only owns the "ask the LLM to pick
one label given some reference text, and cite which reference it used" part.

Prompt convention: every `instruction` string passed into classify()/
extract_json() should be ONLY a ROLE + OBJECTIVE + DECISION RULES block --
what's being decided, and what each option means. Never restate the allowed
outputs (the final JSON-shape line below already renders them from
`verdict_options`) -- _build_prompt()/_build_extraction_prompt() already
supply one shared grounding line ("ground your verdict only in the text and
reference material above; a shared topic is not evidence") for every caller,
so don't re-explain that either. A prompt that starts accumulating its own
"don't confuse X with Y" exception list instead of a general decision rule
is a sign the rule needs to be more general, not that another exception
belongs here.

A more elaborate, explicit multi-step "REASONING PROCESS" block (read the
subject, identify the specific decisive fact, read each reference, compare
by meaning, ground, output) was tried in the shared harness and reverted --
live A/B testing against real RFP criteria (see the two check_*.py modules'
history) showed it made llama3.2:3b MORE prone to false "violation"/
"has_rule" flags, not less: explicitly instructing the model to "identify
the specific fact this decision turns on" before reading references seems
to anchor it on the topic level, and the elaborate scaffold gives it more
room to construct a plausible-sounding connection rather than genuinely
verify one. The single-line "think through your reasoning first" version
below empirically produced fewer false positives on the same test set
while still catching the same genuine violations. If revisiting this,
A/B test against real criteria before trusting a more elaborate prompt --
a good-sounding reasoning procedure is not automatically a better one for
a small model.
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from backend.logging_config import get_logger

load_dotenv()

logger = get_logger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2:3b")
MAX_RETRIES = 3
_CONNECTION_RETRY_DELAY_SECONDS = 5  # only for network errors -- a bad JSON response needs no delay

# Ollama defaults num_ctx to ~2048 tokens regardless of what the model itself
# supports, UNLESS a caller explicitly requests more -- confirmed via a live
# test: a 35k-character prompt and the model's real longest prompt in this
# pipeline (criterion + 5 retrieved norm chunks, ~24k characters) both
# reported the identical prompt_eval_count=2050, and the oversized test
# prompt's own trailing instruction was silently dropped and never answered.
# Every prompt in this file is built as instruction -> references -> subject
# text -> output-format instructions, in that order -- a 2048-token ceiling
# risks silently truncating away the subject text and the output-format
# instructions themselves on any prompt with substantial reference material,
# which no amount of prompt wording can fix. 8192 comfortably covers every
# real prompt measured in this codebase so far and is well within qwen2.5:7b's
# native 32768-token context (confirmed via /api/show) -- raise this further
# if a future prompt (e.g. more retrieved references) genuinely needs it.
_NUM_CTX = 8192


class ReferenceChunk(BaseModel):
    text: str
    citation: dict  # echoed back as-is if this reference is cited — caller decides what it contains


class ClassificationResult(BaseModel):
    verdict: str
    reasoning: str
    citation: dict | None = None


class ExtractionResult(BaseModel):
    data: dict
    reasoning: str
    citation: dict | None = None


class _RawResponse(BaseModel):
    reasoning: str
    verdict: str
    reference_index: int | None = None


class _RawExtraction(BaseModel):
    reasoning: str
    data: dict = {}
    reference_index: int | None = None


def _build_prompt(
    subject_text: str, references: list[ReferenceChunk], verdict_options: list[str], instruction: str
) -> str:
    if references:
        ref_lines = [f"[{i}] {ref.text}" for i, ref in enumerate(references)]
        references_block = "\n\n".join(ref_lines)
    else:
        references_block = "(no reference material retrieved)"

    options_str = " | ".join(verdict_options)

    return f"""{instruction}

Reference material (numbered):
{references_block}

Text to classify:
\"\"\"{subject_text}\"\"\"

Think through your reasoning first, then pick the verdict that your reasoning actually supports -- the verdict must follow from the reasoning, not the other way around.

Respond with ONLY a JSON object, no other text, with the fields in this exact order:
{{"reasoning": "<one to two plain sentences of reasoning, as plain text, not a nested object>", "verdict": "<one of: {options_str}, chosen to match the reasoning above>", "reference_index": <the bracket number of the reference you used, or null if none apply>}}"""


def classify(
    subject_text: str,
    references: list[ReferenceChunk],
    verdict_options: list[str],
    instruction: str,
) -> ClassificationResult:
    prompt = _build_prompt(subject_text, references, verdict_options, instruction)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": LLM_MODEL,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0, "num_ctx": _NUM_CTX},
                },
                timeout=150,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(
                "classify() attempt %d/%d: network error (%s) -- retrying in %ds",
                attempt, MAX_RETRIES + 1, e, _CONNECTION_RETRY_DELAY_SECONDS,
            )
            time.sleep(_CONNECTION_RETRY_DELAY_SECONDS)
            continue

        raw = resp.json()["response"]

        try:
            parsed = _RawResponse.model_validate_json(raw)
        except ValidationError as e:
            last_error = e
            logger.warning("classify() attempt %d/%d: malformed JSON response (%s)", attempt, MAX_RETRIES + 1, e)
            continue

        if parsed.verdict not in verdict_options:
            last_error = ValueError(f"verdict {parsed.verdict!r} not in {verdict_options}")
            logger.warning(
                "classify() attempt %d/%d: verdict %r not in allowed options %s",
                attempt, MAX_RETRIES + 1, parsed.verdict, verdict_options,
            )
            continue

        citation = None
        if parsed.reference_index is not None and 0 <= parsed.reference_index < len(references):
            citation = references[parsed.reference_index].citation

        logger.info("classify() succeeded on attempt %d/%d: verdict=%r", attempt, MAX_RETRIES + 1, parsed.verdict)
        return ClassificationResult(verdict=parsed.verdict, reasoning=parsed.reasoning, citation=citation)

    logger.error("classify() failed after %d attempts: %s", MAX_RETRIES + 1, last_error)
    raise RuntimeError(f"Classification failed after {MAX_RETRIES + 1} attempts: {last_error}")


_CHALLENGE_INSTRUCTION = (
    "ROLE: You are independently re-checking a compliance decision someone else already made, "
    "specifically to test whether their stated reasoning actually holds up.\n"
    "OBJECTIVE: Decide whether the prior conclusion of 'violation' is a genuine, specific "
    "contradiction, or a false match based on a shared topic, shared wording, or restating the "
    "same rule rather than an actual conflict with it.\n"
    "DECISION RULES:\n"
    "- Classify 'confirmed' only if, re-deriving this for yourself from the criterion and "
    "reference below, the reference genuinely states a rule that the criterion directly "
    "contradicts or is incompatible with.\n"
    "- Classify 'not_confirmed' if the criterion merely restates, aligns with, or shares a "
    "topic with the reference without actually contradicting it -- including when the prior "
    "reasoning's own words describe the criterion as 'similar to' or 'identical to' the "
    "reference, or as one of several listed conditions, since matching or being part of a rule "
    "is not the same as breaking it.\n"
    "- Default to skepticism: most flagged violations turn out, on closer inspection, not to "
    "be genuine conflicts -- only classify 'confirmed' if the contradiction is clear and "
    "specific, not merely plausible."
)


def confirm_violation(criterion_text: str, reference: ReferenceChunk, prior_reasoning: str) -> ClassificationResult:
    """Second-pass adversarial check before a 'violation' verdict from
    classify() is ever surfaced to a human as a compliance/prohibited-
    practice flag. Added after repeatedly finding (check_rfp_compliance.py,
    check_prohibited_practices.py) that a single classify() call mistakes
    "the criterion restates/aligns with the reference" for "the criterion
    contradicts it" -- prompt wording alone reduced this but didn't
    eliminate it, recurring on unrelated clause topics each time a new real
    RFP was tested. This re-examines the SAME criterion/reference pair from
    scratch, explicitly skeptical of the first pass's own conclusion, using
    the same classify() primitive and harness -- not a new mechanism, just
    a second, adversarial application of the existing one. Only a
    'confirmed' verdict here should ever reach a buyer as a flag;
    'not_confirmed' downgrades it back to unflagged, same "don't guess"
    discipline as everywhere else in this project, applied one level up."""
    subject_text = (
        f'Criterion: "{criterion_text}"\n\n'
        f'A prior review concluded this is a VIOLATION against the reference below, with this '
        f'reasoning: "{prior_reasoning}"'
    )
    return classify(
        subject_text=subject_text,
        references=[reference],
        verdict_options=["confirmed", "not_confirmed"],
        instruction=_CHALLENGE_INSTRUCTION,
    )


def _build_extraction_prompt(subject_text: str, references: list[ReferenceChunk], instruction: str) -> str:
    if references:
        ref_lines = [f"[{i}] {ref.text}" for i, ref in enumerate(references)]
        references_block = "\n\n".join(ref_lines)
    else:
        references_block = "(no reference material retrieved)"

    return f"""{instruction}

Reference material (numbered):
{references_block}

Text to read:
\"\"\"{subject_text}\"\"\"

Think through your reasoning first, then produce exactly the JSON object your instruction above described, under the "data" key -- respond with an empty object under "data" if you cannot confidently produce it, rather than guessing.

Respond with ONLY a JSON object, no other text, with the fields in this exact order:
{{"reasoning": "<one to two plain sentences of reasoning, as plain text>", "data": <the JSON object described in the instruction above, or {{}} if you can't produce one>, "reference_index": <the bracket number of the reference you used, or null if none apply>}}"""


def extract_json(
    subject_text: str,
    instruction: str,
    references: list[ReferenceChunk] | None = None,
) -> ExtractionResult:
    """Open-ended structured-JSON sibling to classify(): the model returns an
    arbitrary object (`data`) whose exact shape is described entirely by
    `instruction` -- this function only guarantees valid, parseable JSON came
    back (retries MAX_RETRIES times on network error or invalid JSON,
    mirroring classify()'s loop) and grounds `citation` via reference_index
    exactly like classify() does when references are given. The caller
    validates the specific shape of `data` itself (e.g. against the Rule
    discriminated union in backend/models/rule.py) -- this function has no
    idea what shape to expect, and never raises on an empty/unusable `data`,
    only on genuinely malformed JSON after all retries."""
    references = references or []
    prompt = _build_extraction_prompt(subject_text, references, instruction)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": LLM_MODEL,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0, "num_ctx": _NUM_CTX},
                },
                timeout=150,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(
                "extract_json() attempt %d/%d: network error (%s) -- retrying in %ds",
                attempt, MAX_RETRIES + 1, e, _CONNECTION_RETRY_DELAY_SECONDS,
            )
            time.sleep(_CONNECTION_RETRY_DELAY_SECONDS)
            continue

        raw = resp.json()["response"]

        try:
            parsed = _RawExtraction.model_validate_json(raw)
        except ValidationError as e:
            last_error = e
            logger.warning("extract_json() attempt %d/%d: malformed JSON response (%s)", attempt, MAX_RETRIES + 1, e)
            continue

        citation = None
        if parsed.reference_index is not None and 0 <= parsed.reference_index < len(references):
            citation = references[parsed.reference_index].citation

        logger.info("extract_json() succeeded on attempt %d/%d", attempt, MAX_RETRIES + 1)
        return ExtractionResult(data=parsed.data, reasoning=parsed.reasoning, citation=citation)

    logger.error("extract_json() failed after %d attempts: %s", MAX_RETRIES + 1, last_error)
    raise RuntimeError(f"Extraction failed after {MAX_RETRIES + 1} attempts: {last_error}")


if __name__ == "__main__":
    # M8 verification: a clause vs. bid excerpt, run repeatedly to check JSON reliability
    references = [
        ReferenceChunk(
            text="xi. Sellers shall offer minimum discount of 10% on the Maximum Retail Price (MRP) "
            "mandatorily on GeM Marketplace (unless otherwise specified).",
            citation={"norm_name": "GeM General Terms and Conditions", "clause_ref": "xi.", "page_number": 6},
        )
    ]
    subject = "The bidder has offered a 12% discount on MRP for all listed products."

    n_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    successes = 0
    for i in range(n_runs):
        try:
            result = classify(
                subject_text=subject,
                references=references,
                verdict_options=["pass", "fail", "partial", "not_found"],
                instruction="Does the following bid text satisfy or violate the referenced clause? Classify it.",
            )
            successes += 1
            print(f"run {i + 1}: verdict={result.verdict!r} reasoning={result.reasoning!r} citation={result.citation}")
        except RuntimeError as e:
            print(f"run {i + 1}: FAILED — {e}")

    print(f"\n{successes}/{n_runs} runs produced valid, parseable classifications.")

    # Milestone 4 verification: extract_json() against a representative
    # value-extraction task (the shape milestone 7 will actually use it for)
    print("\n--- extract_json() smoke test ---")
    value_subject = "Our Lead Engineer has 12 years of professional experience delivering enterprise IT projects."
    successes = 0
    for i in range(n_runs):
        try:
            result = extract_json(
                subject_text=value_subject,
                instruction=(
                    'Extract the number of years of professional experience described in the text below, '
                    'even if the text uses different wording than "years of experience" (e.g. a named role '
                    'or a paraphrase) -- respond with {"years": <number>} under "data", or {"years": null} '
                    "if no such value is stated."
                ),
            )
            successes += 1
            print(f"run {i + 1}: data={result.data!r} reasoning={result.reasoning!r}")
        except RuntimeError as e:
            print(f"run {i + 1}: FAILED — {e}")
    print(f"\n{successes}/{n_runs} runs produced valid, parseable extractions.")
