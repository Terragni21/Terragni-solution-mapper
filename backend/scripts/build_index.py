from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from document_parser import build_index
idx = build_index()
print(f"Indexed {len(idx['documents'])} chunks from {len(idx['fingerprints'])} documents.")
