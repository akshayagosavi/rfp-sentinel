"""
M8: generic LLM classifier — the single reusable function behind both
check_rfp_compliance (M9, verdicts: compliant/violation/unclear) and
retrieve_and_extract_evidence (M11, verdicts: pass/fail/partial/not_found).

Not compliance-specific or bid-specific — the caller supplies the verdict
labels and the instruction, this module only owns the "ask the LLM to pick
one label given some reference text, and cite which reference it used" part.
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
MAX_RETRIES = 2
_CONNECTION_RETRY_DELAY_SECONDS = 3  # only for network errors -- a bad JSON response needs no delay


class ReferenceChunk(BaseModel):
    text: str
    citation: dict  # echoed back as-is if this reference is cited — caller decides what it contains


class ClassificationResult(BaseModel):
    verdict: str
    reasoning: str
    citation: dict | None = None


class _RawResponse(BaseModel):
    reasoning: str
    verdict: str
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

Think through your reasoning first, then pick the verdict that your reasoning actually supports — the verdict must follow from the reasoning, not the other way around.

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
                    "options": {"temperature": 0},
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
