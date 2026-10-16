from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BACKEND_DIR = PROJECT_ROOT / "backend"


# ============================================================
# MAKE BACKEND IMPORTABLE
# ============================================================

# Allows this file to be executed directly with:
#
#     python backend\ingestion\pipeline.py
#

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ============================================================
# INGESTION IMPORTS
# ============================================================

from ingestion.chunker import clean_text, split_text
from ingestion.docx_extractor import extract_docx
from ingestion.pdf_extractor import extract_pdf
from ingestion.pptx_extractor import extract_pptx


# ============================================================
# DATA DIRECTORIES
# ============================================================

DATA_DIR = BACKEND_DIR / "data1"

RAW_PDF_DIR = DATA_DIR / "raw" / "pdf"
RAW_PPTX_DIR = DATA_DIR / "raw" / "pptx"
RAW_DOCX_DIR = DATA_DIR / "raw" / "docx"

PROCESSED_DIR = DATA_DIR / "processed"

TEST_OUTPUT_DIR = (
    PROCESSED_DIR / "test_output"
)


# ============================================================
# WINDOWS-SAFE PATH
# ============================================================

def windows_safe_path(
    path: Path,
) -> str:
    """
    Return a Windows-safe absolute path.

    Windows can have problems with very long paths.
    The extended-length path prefix allows Python to
    access long source filenames.

    On non-Windows systems, the normal absolute path
    is returned.
    """

    path = path.resolve()

    if sys.platform == "win32":

        path_string = str(path)

        if not path_string.startswith(
            "\\\\?\\"
        ):
            return "\\\\?\\" + path_string

        return path_string

    return str(path)


# ============================================================
# FILE HASH
# ============================================================

def calculate_file_hash(
    path: Path,
) -> str:
    """
    Calculate SHA-256 hash for the original
    source document.

    The hash is later used by the Oracle
    ingestion layer to detect duplicates.
    """

    sha256 = hashlib.sha256()

    safe_path = windows_safe_path(
        path
    )

    with open(
        safe_path,
        "rb",
    ) as file:

        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha256.update(block)

    return sha256.hexdigest()


# ============================================================
# DOCUMENT TYPE
# ============================================================

def document_type_for(
    path: Path,
) -> str:
    """
    Return the technical document type.

    This is only a file-format classification.
    Business classification happens separately.
    """

    extension = path.suffix.lower()

    if extension == ".pdf":
        return "PDF"

    if extension == ".pptx":
        return "PPTX"

    if extension == ".docx":
        return "DOCX"

    return "UNKNOWN"


# ============================================================
# EXTRACT DOCUMENT
# ============================================================

def extract_document(
    path: Path,
) -> list[dict]:
    """
    Extract one source document into section records.

    PDF:
        page -> section

    PPTX:
        slide -> section

    DOCX:
        document section -> section
    """

    extension = path.suffix.lower()

    # --------------------------------------------------------
    # Use Windows-safe path for the actual file operation.
    # --------------------------------------------------------

    safe_path = windows_safe_path(
        path
    )

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    if extension == ".pdf":

        extracted = extract_pdf(
            safe_path
        )

        return [
            {
                "section_type": "PAGE",

                "page_number": item.get(
                    "page_number"
                ),

                "slide_number": None,

                "section_order": item.get(
                    "page_number"
                ),

                "section_title": None,

                "text": item.get(
                    "text",
                    "",
                ),
            }

            for item in extracted
        ]

    # --------------------------------------------------------
    # PPTX
    # --------------------------------------------------------

    if extension == ".pptx":

        extracted = extract_pptx(
            safe_path
        )

        return [
            {
                "section_type": "SLIDE",

                "page_number": None,

                "slide_number": item.get(
                    "slide_number"
                ),

                "section_order": item.get(
                    "slide_number"
                ),

                "section_title": None,

                "text": item.get(
                    "text",
                    "",
                ),
            }

            for item in extracted
        ]

    # --------------------------------------------------------
    # DOCX
    # --------------------------------------------------------

    if extension == ".docx":

        extracted = extract_docx(
            safe_path
        )

        return [
            {
                "section_type": "DOCX_SECTION",

                "page_number": None,

                "slide_number": None,

                "section_order": item.get(
                    "section_order"
                ),

                "section_title": item.get(
                    "section_title"
                ),

                "text": item.get(
                    "text",
                    "",
                ),
            }

            for item in extracted
        ]

    raise ValueError(
        f"Unsupported document type: "
        f"{path.suffix}"
    )


# ============================================================
# BUILD DOCUMENT RECORD
# ============================================================

def build_document_record(
    path: Path,
) -> dict:
    """
    Build document-level metadata.

    This maps conceptually to the Oracle DOCUMENT table.

    No Oracle write occurs here.
    """

    return {
        "title": path.stem,

        "file_name": path.name,

        "file_type": (
            path.suffix
            .lower()
            .lstrip(".")
        ),

        "document_type": (
            document_type_for(path)
        ),

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Store the normal relative source path.
        # Do NOT store the Windows \\?\ prefix.
        # ----------------------------------------------------

        "source_path": str(
            path.relative_to(
                PROJECT_ROOT
            )
        ),

        "file_hash": (
            calculate_file_hash(
                path
            )
        ),

        "ingestion_status": "EXTRACTED",
    }


# ============================================================
# BUILD SECTIONS AND CHUNKS
# ============================================================

def build_sections_and_chunks(
    extracted_sections: list[dict],
) -> list[dict]:
    """
    Clean extracted text and create chunks.

    Structure:

        section
          |
          +-- text
          |
          +-- chunks
                |
                +-- chunk 1
                +-- chunk 2
                +-- ...
    """

    results: list[dict] = []

    for section in extracted_sections:

        # ----------------------------------------------------
        # Raw extracted text
        # ----------------------------------------------------

        raw_text = section.get(
            "text",
            "",
        )

        # ----------------------------------------------------
        # Clean text
        # ----------------------------------------------------

        cleaned_text = clean_text(
            raw_text
        )

        # ----------------------------------------------------
        # Chunk text
        #
        # A page containing only a confidentiality footer
        # can correctly produce zero chunks.
        # ----------------------------------------------------

        chunks = split_text(
            cleaned_text,
            max_chars=4500,
            overlap_chars=500,
        )

        # ----------------------------------------------------
        # Build chunk records
        # ----------------------------------------------------

        chunk_records: list[dict] = []

        for chunk_order, chunk_text in enumerate(
            chunks,
            start=1,
        ):

            chunk_text = (
                chunk_text.strip()
            )

            if not chunk_text:
                continue

            chunk_records.append(
                {
                    "chunk_order": chunk_order,

                    "token_count": len(
                        chunk_text.split()
                    ),

                    "text": chunk_text,
                }
            )

        # ----------------------------------------------------
        # Build section record
        # ----------------------------------------------------

        section_record = {
            "section_type": section.get(
                "section_type"
            ),

            "page_number": section.get(
                "page_number"
            ),

            "slide_number": section.get(
                "slide_number"
            ),

            "section_order": section.get(
                "section_order"
            ),

            "section_title": section.get(
                "section_title"
            ),

            "text": cleaned_text,

            "chunks": chunk_records,
        }

        results.append(
            section_record
        )

    return results


# ============================================================
# PROCESS ONE DOCUMENT
# ============================================================

def process_document(
    path: Path,
) -> dict:
    """
    Process one source document into an intermediate
    structured representation.

    No Oracle writes occur here.
    """

    document = build_document_record(
        path
    )

    extracted_sections = (
        extract_document(path)
    )

    sections = (
        build_sections_and_chunks(
            extracted_sections
        )
    )

    total_chunks = sum(
        len(
            section.get(
                "chunks",
                [],
            )
        )
        for section in sections
    )

    return {
        "document": document,

        "sections": sections,

        "summary": {
            "section_count": len(
                sections
            ),

            "chunk_count": total_chunks,
        },
    }


# ============================================================
# DISCOVER SOURCE DOCUMENTS
# ============================================================

def discover_source_documents() -> list[Path]:
    """
    Discover all supported Terragni source documents.

    Supported:

        PDF
        PPTX
        DOCX
    """

    paths: list[Path] = []

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    if RAW_PDF_DIR.exists():

        paths.extend(
            RAW_PDF_DIR.glob(
                "*.pdf"
            )
        )

    # --------------------------------------------------------
    # PPTX
    # --------------------------------------------------------

    if RAW_PPTX_DIR.exists():

        paths.extend(
            RAW_PPTX_DIR.glob(
                "*.pptx"
            )
        )

    # --------------------------------------------------------
    # DOCX
    # --------------------------------------------------------

    if RAW_DOCX_DIR.exists():

        paths.extend(
            RAW_DOCX_DIR.glob(
                "*.docx"
            )
        )

    # --------------------------------------------------------
    # Remove duplicate paths
    # --------------------------------------------------------

    unique_paths = {
        path.resolve()
        for path in paths
    }

    return sorted(
        unique_paths,
        key=lambda path: str(
            path
        ).lower(),
    )


# ============================================================
# SAFE OUTPUT FILENAME
# ============================================================

def build_output_filename(
    title: str,
) -> str:
    """
    Build a Windows-safe processed JSON filename.

    The original source filename is NOT changed.

    Only the generated JSON filename is shortened.

    This prevents Windows path-length problems when a
    source document has a very long filename.
    """

    # Keep generated filenames comfortably below
    # Windows path limits.

    max_title_length = 80

    safe_title = (
        title
        .strip()
        .rstrip(". ")
    )

    if not safe_title:

        safe_title = "document"

    if len(safe_title) > max_title_length:

        safe_title = (
            safe_title[
                :max_title_length
            ]
            .rstrip()
            .rstrip(".")
        )

    return (
        f"{safe_title}.json"
    )


# ============================================================
# SAVE PROCESSED DOCUMENT
# ============================================================

def save_processed_document(
    result: dict,
    output_directory: Path,
) -> Path:
    """
    Save one processed document as JSON.

    The original document metadata remains unchanged.

    Only the generated JSON filename is shortened when
    necessary.
    """

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    title = result[
        "document"
    ][
        "title"
    ]

    output_filename = (
        build_output_filename(
            title
        )
    )

    output_path = (
        output_directory
        / output_filename
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


# ============================================================
# RUN INGESTION
# ============================================================

def run_ingestion(
    limit: int | None = None,
    output_directory: Path = PROCESSED_DIR,
) -> list[dict]:
    """
    Process source documents and save intermediate JSON.

    This function does NOT write to Oracle.

    Parameters
    ----------
    limit:
        Number of documents to process.

        None = process all documents.

    output_directory:
        Directory where processed JSON files are written.
    """

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    documents = (
        discover_source_documents()
    )

    # --------------------------------------------------------
    # Optional limit
    # --------------------------------------------------------

    if limit is not None:

        documents = (
            documents[:limit]
        )

    results: list[dict] = []

    print()
    print("=" * 70)
    print(
        "TERRAGNI DOCUMENT INGESTION"
    )
    print("=" * 70)

    print(
        f"Documents discovered : "
        f"{len(documents)}"
    )

    print(
        f"Output directory     : "
        f"{output_directory}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # Process documents
    # --------------------------------------------------------

    for index, path in enumerate(
        documents,
        start=1,
    ):

        print()
        print(
            f"[{index}/{len(documents)}] "
            f"Processing: {path.name}"
        )

        try:

            result = process_document(
                path
            )

            output_path = (
                save_processed_document(
                    result,
                    output_directory,
                )
            )

            section_count = (
                result[
                    "summary"
                ][
                    "section_count"
                ]
            )

            chunk_count = (
                result[
                    "summary"
                ][
                    "chunk_count"
                ]
            )

            document_type = (
                result[
                    "document"
                ][
                    "document_type"
                ]
            )

            print(
                f"  Type     : "
                f"{document_type}"
            )

            print(
                f"  Sections : "
                f"{section_count}"
            )

            print(
                f"  Chunks   : "
                f"{chunk_count}"
            )

            print(
                f"  Output   : "
                f"{output_path}"
            )

            results.append(
                result
            )

        except Exception as exc:

            # ------------------------------------------------
            # Do not stop the complete batch because of
            # one problematic document.
            # ------------------------------------------------

            print(
                f"  ERROR    : "
                f"{exc}"
            )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print(
        "INGESTION PROCESSING COMPLETE"
    )
    print("=" * 70)

    print(
        f"Successfully processed : "
        f"{len(results)}"
    )

    print(
        f"Discovered              : "
        f"{len(documents)}"
    )

    failed_count = (
        len(documents)
        - len(results)
    )

    print(
        f"Failed                  : "
        f"{failed_count}"
    )

    print("=" * 70)
    print()

    return results


# ============================================================
# COMMAND-LINE ENTRY POINT
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # FULL TERRAGNI LIBRARY
    #
    # None = process all supported source documents.
    # --------------------------------------------------------

    run_ingestion(
        limit=None,
        output_directory=PROCESSED_DIR,
    )