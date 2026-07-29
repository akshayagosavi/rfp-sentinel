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

Uses the shared extract_json() primitive (backend/llm/ollama_client.py)
rather than its own request/retry loop -- this used to duplicate that
machinery independently; now it gets the same retry count and grounding
discipline as every other prompt in this codebase for free.
"""
from pydantic import BaseModel

from backend.llm.ollama_client import extract_json
from backend.logging_config import get_logger
from backend.rag.qdrant_client import get_bid_packet_text, get_client

logger = get_logger(__name__)

_INSTRUCTION = (
    "ROLE: You are reading a bidder's financial bid / price schedule document submitted for a "
    "government tender.\n"
    "OBJECTIVE: Find and extract the single TOTAL bid price -- the final grand total the "
    "bidder is offering.\n"
    "DECISION RULES:\n"
    "- The value you want is the bidder's own final grand total actually payable, not a "
    "per-unit rate, a subtotal, or an individual tax/duty line.\n"
    "- If the document states multiple totals (e.g. a pre-tax and a post-tax figure), prefer "
    "whichever is described as the final amount actually payable.\n"
    '- Respond with {"price": <the total as a plain number, no currency symbols, commas, or '
    'units>} under "data".\n'
    '- Respond with {"price": null} under "data" if no total price is stated anywhere in the '
    "document -- do not calculate, sum, or estimate a total from unit rates and quantities; "
    "only report a total the document itself actually states as such."
)


class BidPriceResult(BaseModel):
    price: float | None
    reasoning: str


def extract_bid_price(bid_id: str) -> BidPriceResult:
    client = get_client()
    document_text = get_bid_packet_text(client, bid_id, packet="II")
    if not document_text.strip():
        return BidPriceResult(price=None, reasoning="No Packet-II (financial) content found for this bid.")

    try:
        result = extract_json(subject_text=document_text, instruction=_INSTRUCTION, references=[])
    except RuntimeError as e:
        # Same discipline as the rest of this project: an extraction that
        # never produced a usable answer is a "don't know," not a crash --
        # the caller (run_stage2_evaluation) excludes this bid from ranking
        # and logs it for human follow-up, rather than losing every other
        # bid's results too.
        logger.error("extract_bid_price(bid_id=%r) failed: %s", bid_id, e)
        return BidPriceResult(price=None, reasoning=f"Extraction failed: {e}")

    price = result.data.get("price")
    logger.info("extract_bid_price(bid_id=%r): price=%s", bid_id, price)
    return BidPriceResult(price=price, reasoning=result.reasoning)
