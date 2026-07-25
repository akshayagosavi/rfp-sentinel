"""
Stage 2's price-extraction step -- turns a bidder's sealed financial
document (Packet-II) into a single number to rank on. Bid submission
deliberately does NOT collect price as a typed field (see backend/db.py's
bids.price comment); the real number only gets read here, when Packet-II
is opened, which only happens via the buyer's explicit "Open Financial
Bids" action (backend/api/rfp.py) -- never automatically after Stage 1,
mirroring GFR Rule 189's two-envelope principle that a technically
disqualified bidder's price is never even looked at.

Goes straight to the LLM, no deterministic regex pre-pass -- unlike the
numeric-threshold comparisons check_rfp_compliance originally needed a
regex fallback for (see that module's docstring: removed once a larger
model proved reliable at numeric reasoning), extracting "the one total
price figure" out of a free-form price-schedule document is a harder
pattern-matching problem than a plain threshold comparison, and this
model has already been confirmed reliable at numeric reasoning. Revisit
with a regex pre-pass only if this proves unreliable in practice.
"""
import os
import time

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from backend.logging_config import get_logger
from backend.rag.qdrant_client import get_bid_packet_text, get_client

load_dotenv()

logger = get_logger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2:3b")
MAX_RETRIES = 2
_CONNECTION_RETRY_DELAY_SECONDS = 3


class BidPriceResult(BaseModel):
    price: float | None
    reasoning: str


class _RawPriceResponse(BaseModel):
    reasoning: str
    price: float | None = None


_PROMPT_TEMPLATE = """The text below is a bidder's financial bid / price schedule document, submitted for a government tender.

Find the single TOTAL bid price/value -- the final grand total the bidder is offering, not a per-unit rate, subtotal, or tax line. If the document lists multiple totals (e.g. before and after tax), prefer the final grand total actually payable.

Document text:
\"\"\"{document_text}\"\"\"

Respond with ONLY a JSON object, no other text, with the fields in this exact order:
{{"reasoning": "<one to two plain sentences identifying which figure you picked and why>", "price": <the total price as a plain number, no currency symbols or commas, or null if no total price is stated anywhere in the document>}}"""


def extract_bid_price(bid_id: str) -> BidPriceResult:
    client = get_client()
    document_text = get_bid_packet_text(client, bid_id, packet="II")
    if not document_text.strip():
        return BidPriceResult(price=None, reasoning="No Packet-II (financial) content found for this bid.")

    prompt = _PROMPT_TEMPLATE.format(document_text=document_text)

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
                "extract_bid_price(bid_id=%r) attempt %d/%d: network error (%s)",
                bid_id, attempt, MAX_RETRIES + 1, e,
            )
            time.sleep(_CONNECTION_RETRY_DELAY_SECONDS)
            continue

        raw = resp.json()["response"]
        try:
            parsed = _RawPriceResponse.model_validate_json(raw)
        except ValidationError as e:
            last_error = e
            logger.warning(
                "extract_bid_price(bid_id=%r) attempt %d/%d: malformed JSON (%s)",
                bid_id, attempt, MAX_RETRIES + 1, e,
            )
            continue

        logger.info(
            "extract_bid_price(bid_id=%r) succeeded on attempt %d/%d: price=%s",
            bid_id, attempt, MAX_RETRIES + 1, parsed.price,
        )
        return BidPriceResult(price=parsed.price, reasoning=parsed.reasoning)

    # Same discipline as the rest of this project: an extraction that never
    # produced a usable answer is a "don't know," not a crash -- the caller
    # (run_stage2_evaluation) excludes this bid from ranking and logs it for
    # human follow-up, rather than losing every other bid's results too.
    logger.error("extract_bid_price(bid_id=%r) failed after %d attempts: %s", bid_id, MAX_RETRIES + 1, last_error)
    return BidPriceResult(price=None, reasoning=f"Extraction failed after {MAX_RETRIES + 1} attempts: {last_error}")
