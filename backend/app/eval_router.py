"""
Kept for backwards compatibility.

The old router evaluation imported functions that no longer exist.
The working evaluation now lives in backend/evaluation/evaluator.py:

    python -m backend.evaluation.evaluator
"""

import sys

from backend.evaluation.evaluator import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
