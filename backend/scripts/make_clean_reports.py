"""
Create CLEAN versions of the Terragni reports (no client names, no contact
details) as Word files, ready for review and upload.

Everything runs on THIS computer. Nothing is sent to any online service.

Usage (from the project folder):

    python -m backend.scripts.make_clean_reports

    Options:
      --input   folder with the ORIGINAL reports (PDF / PPTX / DOCX)
                default: backend/data1/raw
      --output  folder for the CLEAN Word files
                default: backend/data1/clean_reports_draft
      --names   CSV file of client names and their replacements
                default: backend/data/client_names.csv

What it does for every report:
  1. reads the text page by page (PDF), slide by slide (PPTX) or
     paragraph by paragraph (DOCX) - logos and images are dropped;
  2. replaces every client name in client_names.csv with its neutral
     description (e.g. "Example Bank" -> "a leading private bank");
  3. removes emails, phone numbers, website links and account numbers;
  4. writes one clean Word file per report;
  5. writes REVIEW_NOTES.txt listing lines a person must check
     (amounts of money, percentages, "confidential", people's names...).

A person at Terragni MUST read every clean file before it is uploaded.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
for path in (PROJECT_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from docx import Document  # noqa: E402

from ingestion.docx_extractor import extract_docx  # noqa: E402
from ingestion.pdf_extractor import extract_pdf  # noqa: E402
from ingestion.pptx_extractor import extract_pptx  # noqa: E402

DEFAULT_INPUT = BACKEND_DIR / "data1" / "raw"
DEFAULT_OUTPUT = BACKEND_DIR / "data1" / "clean_reports_draft"
DEFAULT_NAMES = BACKEND_DIR / "data" / "client_names.csv"

SUPPORTED = {".pdf", ".pptx", ".docx"}

# ------------------------------------------------------------
# Template for client_names.csv (created the first time).
# Left column: the name as it appears in reports (any spelling).
# Right column: what to write instead.
# The real list lives ONLY in backend/data/client_names.csv on this
# computer (git-ignored) - never put real client names in this code.
# ------------------------------------------------------------
NAMES_TEMPLATE = [
    ("name_in_reports", "replace_with"),
    ("Example Bank Ltd", "a leading private bank"),
    ("Example Bank", "a leading private bank"),
    ("Example Programme Name", "the bank's premium banking programme"),
    ("Example Insurance Co", "a leading life insurer"),
]

# ------------------------------------------------------------
# Patterns
# ------------------------------------------------------------
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)(?!\w)")
ACCOUNT_RE = re.compile(
    r"\b(?:a/c|acct|account|policy|customer|client)\s*(?:no\.?|number|id)?\s*[:#-]?\s*(?=[A-Z0-9-]*\d)[A-Z0-9-]{5,}\b",
    re.IGNORECASE,
)

# Lines a person should look at (not removed automatically).
FLAG_RULES = [
    ("money amount", re.compile(r"(₹|\bRs\.?\s?\d|\bINR\b|\$\s?\d|\b\d[\d,.]*\s?(crore|cr|lakh|lac|mn|million|bn|billion)\b)", re.IGNORECASE)),
    ("percentage / result figure", re.compile(r"\b\d+(\.\d+)?\s?%")),
    ("marked confidential", re.compile(r"\b(confidential|proprietary|internal use only|do not share)\b", re.IGNORECASE)),
    ("person's name", re.compile(r"\b(Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+[A-Z][a-z]+")),
    ("labelled name", re.compile(r"\b(client|company|bank|brand|project)\s*name\s*[:=-]", re.IGNORECASE)),
]


# ============================================================
# CLIENT NAMES
# ============================================================

def load_client_names(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(NAMES_TEMPLATE)
        print(f"Created {path}")
        print("Please open it, check and add ALL client names, then run again.")
        sys.exit(0)

    names: list[tuple[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            if len(row) < 2 or not row[0].strip():
                continue
            if row[0].strip().lower() == "name_in_reports":
                continue
            names.append((row[0].strip(), row[1].strip() or "a client"))

    # Longest names first, so "Example Bank Ltd" is replaced before "Example Bank".
    names.sort(key=lambda item: len(item[0]), reverse=True)
    return names


def build_name_patterns(names):
    patterns = []
    for name, replacement in names:
        # Spaces in a name also match "_", "-" or nothing ("AcmeBank").
        escaped = re.escape(name).replace(r"\ ", r"[\s_\-]*")
        patterns.append((re.compile(rf"(?<![\w]){escaped}(?![\w])", re.IGNORECASE), replacement, name))
    return patterns


# ============================================================
# CLEANING
# ============================================================

# Characters allowed in Word/XML: tab, newline, CR and the normal Unicode
# ranges. Everything else (control codes, broken surrogates, U+FFFE/FFFF)
# would crash python-docx, so it is replaced with a space.
_XML_INVALID_RE = re.compile(
    "[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)


def xml_safe(value: str) -> str:
    return _XML_INVALID_RE.sub(" ", str(value or ""))


def clean_text(text: str, name_patterns, counts: dict) -> str:
    value = str(text or "")

    # Word files cannot contain control characters. PowerPoint uses
    # \x0b (vertical tab) as a line break inside text boxes.
    value = value.replace("\x0b", "\n").replace("\x0c", "\n")
    value = xml_safe(value)

    # Remove contact details FIRST (before names are replaced inside them).
    value = EMAIL_RE.sub("[email removed]", value)
    value = URL_RE.sub("[link removed]", value)
    value = ACCOUNT_RE.sub("[reference removed]", value)
    value = PHONE_RE.sub("[phone removed]", value)

    for pattern, replacement, name in name_patterns:
        def substitute(match, replacement=replacement):
            before = match.string[:match.start()]
            # Capitalise at the start of the text, a sentence or a line.
            if not before.strip() or re.search(r"([.!?:]\s*|\n\s*)$", before):
                return replacement[:1].upper() + replacement[1:]
            return replacement

        value, n = pattern.subn(substitute, value)
        if n:
            counts[name] = counts.get(name, 0) + n

    # Tidy doubled words created by replacements:
    # "the a leading bank" -> "a leading bank", "the the bank's" -> "the bank's"
    value = re.sub(r"\b(the|The)\s+(a|an|A|An)\s+", lambda m: (m.group(2).capitalize() if m.group(1) == "The" else m.group(2).lower()) + " ", value)
    value = re.sub(r"\b(the|The)\s+(the|The)\b", lambda m: m.group(1), value)
    return value.strip()


def flag_lines(text: str) -> list[tuple[str, str]]:
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for label, rule in FLAG_RULES:
            if rule.search(line):
                found.append((label, line[:200]))
                break
    return found


def read_sections(path: Path) -> list[tuple[str, str]]:
    """Return [(heading, text)] - one entry per page / slide / paragraph."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return [(f"Page {s.get('page_number', i)}", s.get("text", "")) for i, s in enumerate(extract_pdf(path), 1)]
    if suffix == ".pptx":
        return [(f"Slide {s.get('slide_number', i)}", s.get("text", "")) for i, s in enumerate(extract_pptx(path), 1)]
    return [(s.get("section_title") or f"Section {i}", s.get("text", "")) for i, s in enumerate(extract_docx(path), 1)]


def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name.replace("'", "")
    # Keep names short: Windows refuses full paths longer than ~260 characters.
    name = name or "Clean report"
    if len(name) > 80:
        name = name[:80].rsplit(" ", 1)[0]
    name = name.rstrip(" .-&")
    return name or "Clean report"


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Create clean Terragni reports.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--names", default=str(DEFAULT_NAMES))
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    names = load_client_names(Path(args.names))
    patterns = build_name_patterns(names)

    files = sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        print(f"No PDF / PPTX / DOCX files found in {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    seen_titles: set[str] = set()

    print(f"Client names loaded: {len(names)}")
    print(f"Reports found      : {len(files)}")
    print("-" * 60)

    for path in files:
        counts: dict[str, int] = {}
        try:
            sections = read_sections(path)
        except Exception as exc:
            print(f"SKIPPED {path.name}: {exc}")
            notes.append(f"\n### {path.name}\n  SKIPPED - could not read: {exc}")
            continue

        full_title = clean_text(path.stem.replace("_", " "), patterns, counts)
        title = safe_filename(full_title)
        if title.lower() in seen_titles:
            print(f"  duplicate of an earlier report, skipped: {path.name}")
            continue
        seen_titles.add(title.lower())

        document = Document()
        document.add_heading(xml_safe(full_title), level=1)
        flags: list[tuple[str, str]] = []
        kept = 0

        for heading, text in sections:
            cleaned = clean_text(text, patterns, counts)
            if not cleaned:
                continue
            document.add_heading(xml_safe(heading), level=2)
            document.add_paragraph(cleaned)
            flags.extend((f"{heading}: {label}", line) for label, line in flag_lines(cleaned))
            kept += 1

        out_path = output_dir / f"{title}.docx"
        document.save(str(out_path))

        replaced = sum(counts.values())
        print(f"OK  {out_path.name}  ({kept} sections, {replaced} names replaced, {len(flags)} lines to check)")

        notes.append(f"\n### {out_path.name}\n  Original file : {path.name}")
        notes.append("  Names replaced: " + (", ".join(f"{k} x{v}" for k, v in counts.items()) or "none"))
        if flags:
            notes.append("  PLEASE CHECK these lines:")
            notes.extend(f"   - [{where}] {line}" for where, line in flags)
        else:
            notes.append("  Nothing flagged - still read the whole file once.")

    review = output_dir / "REVIEW_NOTES.txt"
    review.write_text(
        "CLEAN REPORTS - REVIEW CHECKLIST\n"
        "================================\n"
        "Before uploading, a Terragni team member must open EVERY clean Word file and:\n"
        "  1. confirm no client name, brand/programme name or person's name remains;\n"
        "  2. decide whether each flagged figure (money, %) may be shared - delete it if not;\n"
        "  3. remove anything else confidential, then save the file.\n"
        "If a client name was missed, add it to backend/data/client_names.csv and run the script again.\n"
        + "\n".join(notes)
        + "\n",
        encoding="utf-8",
    )
    print("-" * 60)
    print(f"Clean Word files : {output_dir}")
    print(f"Review checklist : {review}")


if __name__ == "__main__":
    main()
