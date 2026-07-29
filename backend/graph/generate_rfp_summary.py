"""
Bidder-facing plain-language RFP summary -- a few sentences explaining
what's being procured, who's eligible, and how it'll be evaluated, so a
bidder can get the gist without reading the full RFP PDF. Purely
explanatory: it never feeds back into evaluation or scoring, only ever
displayed. Cached in Postgres (rfps.summary, see backend/db.py) after
first generation -- the RFP's content is immutable once published, so
regenerating an identical summary on every page view would just be
wasted LLM calls.
"""
import os
import time

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from backend.logging_config import get_logger
from backend.models.rfp import StructuredRFP

load_dotenv()

logger = get_logger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2:3b")
MAX_RETRIES = 3
_CONNECTION_RETRY_DELAY_SECONDS = 3

# See backend/llm/ollama_client.py's _NUM_CTX for why this must be set
# explicitly -- Ollama otherwise silently truncates to ~2048 tokens
# regardless of what the model supports, which risks cutting off the
# trailing output-format instructions on a large-criteria-list RFP.
_NUM_CTX = 8192

# Capped, not the full criteria list -- keeps the prompt bounded on a large
# RFP (real ones have run 20-30+ criteria) and a summary only needs the
# gist, not an exhaustive restatement of every clause.
_MAX_CRITERIA_IN_PROMPT = 20


class _RawSummaryResponse(BaseModel):
    summary: str


_PROMPT_TEMPLATE = """The text below lists eligibility and technical criteria extracted from a government tender (RFP), evaluated by the "{evaluation_method}" method in the "{category}" category.

Criteria:
{criteria_text}

Write a short, plain-language summary (3-5 sentences) for a prospective bidder who hasn't read the full tender document yet: what is being procured, who is eligible to bid, and how the winner will be selected. Do not restate every criterion -- summarize the overall shape of the requirement. Avoid legal/procurement jargon where a simpler word works.

Respond with ONLY a JSON object, no other text: {{"summary": "<the plain-language summary as one paragraph>"}}"""


def generate_rfp_summary(structured_rfp: StructuredRFP) -> str:
    criteria_text = "\n".join(f"- {c.text}" for c in structured_rfp.criteria[:_MAX_CRITERIA_IN_PROMPT])
    prompt = _PROMPT_TEMPLATE.format(
        evaluation_method=structured_rfp.evaluation_method,
        category=structured_rfp.category,
        criteria_text=criteria_text or "(no criteria extracted)",
    )

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
                "generate_rfp_summary(rfp_id=%r) attempt %d/%d: network error (%s)",
                structured_rfp.rfp_id, attempt, MAX_RETRIES + 1, e,
            )
            time.sleep(_CONNECTION_RETRY_DELAY_SECONDS)
            continue

        raw = resp.json()["response"]
        try:
            parsed = _RawSummaryResponse.model_validate_json(raw)
        except ValidationError as e:
            last_error = e
            logger.warning(
                "generate_rfp_summary(rfp_id=%r) attempt %d/%d: malformed JSON (%s)",
                structured_rfp.rfp_id, attempt, MAX_RETRIES + 1, e,
            )
            continue

        logger.info("generate_rfp_summary(rfp_id=%r) succeeded on attempt %d/%d", structured_rfp.rfp_id, attempt, MAX_RETRIES + 1)
        return parsed.summary

    logger.error("generate_rfp_summary(rfp_id=%r) failed after %d attempts: %s", structured_rfp.rfp_id, MAX_RETRIES + 1, last_error)
    raise RuntimeError(f"Summary generation failed after {MAX_RETRIES + 1} attempts: {last_error}")
