"""
Document-completeness check -- a fast, cheap presence check, separate from
and earlier than retrieve_and_extract_evidence.py's per-criterion content
matching. Answers "did the bidder submit every document TYPE the RFP said
was required" (e.g. "Experience Criteria", "Past Performance"), not "does
the content satisfy the requirement" -- that's a different question,
answered by a different, more expensive step.

Matching is deliberately simple (normalized substring containment) -- a
quick first pass a human evaluator could sanity-check in seconds, not a
claim that filenames are a reliable proof of content. A bidder naming their
file "experience.pdf" instead of "Experience Criteria.pdf" would still
match; a bidder naming it something unrelated would correctly show as
missing even if the content happens to be right -- that's the honest
limitation of a filename-based check, not a bug to silently paper over.
"""
import re
import sys
from pathlib import Path


def _normalize(name: str) -> str:
    name = Path(name).stem  # drop .pdf/.xlsx extension
    name = re.sub(r"\(.*?\)", "", name)  # drop parenthetical notes like "(Requested in ATC)"
    return re.sub(r"[^a-z0-9]", "", name.lower())


def check_document_completeness(required_documents: list[str], uploaded_filenames: list[str]) -> dict:
    normalized_uploaded = [(_normalize(f), f) for f in uploaded_filenames]
    present = []
    missing = []
    for doc in required_documents:
        norm_doc = _normalize(doc)
        match = next((orig for norm, orig in normalized_uploaded if norm_doc and (norm_doc in norm or norm in norm_doc)), None)
        if match:
            present.append({"required": doc, "matched_file": match})
        else:
            missing.append(doc)
    return {"present": present, "missing": missing}


if __name__ == "__main__":
    from backend.graph.extract_rfp_criteria import extract_rfp_criteria
    from backend.rag.qdrant_client import get_bid_source_files, get_client

    rfp_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/rfps/47887e14_Gem Bid Document.pdf")
    bid_id = sys.argv[2] if len(sys.argv) > 2 else "4670f967"

    rfp = extract_rfp_criteria(rfp_path, rfp_id="test-rfp-1")
    uploaded = get_bid_source_files(get_client(), bid_id, packet="I")

    result = check_document_completeness(rfp.required_documents, uploaded)

    print(f"RFP requires {len(rfp.required_documents)} document types")
    print(f"Bidder uploaded {len(uploaded)} Packet-I files: {uploaded}\n")

    print(f"PRESENT ({len(result['present'])}):")
    for item in result["present"]:
        print(f"  - {item['required']!r} <- matched {item['matched_file']!r}")

    print(f"\nMISSING ({len(result['missing'])}):")
    for doc in result["missing"]:
        print(f"  - {doc!r}")
