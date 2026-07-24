"""
Central logging setup. Every long-running, LLM-heavy step (RFP extraction,
compliance-check, evidence-check) logs its progress and errors here instead
of relying on print() -- built after a real incident where a dropped
connection to the remote Ollama server crashed a 10+ minute extraction run
with zero visibility into how far it had gotten or what actually failed.

One log file, appended across runs (not rotated/dated) -- simplest thing
that works for a single-machine demo; revisit only if the file becomes a
real problem to read.
"""
import logging
import sys
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "rfp_sentinel.log"

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        LOG_DIR.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler(sys.stdout),
            ],
        )
        _configured = True
    return logging.getLogger(name)
