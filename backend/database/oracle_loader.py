from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from connection import get_connection


# ============================================================
# PATH CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = (
    PROJECT_ROOT
    / "backend"
    / "data1"
    / "processed"
)


# ============================================================
# DISPLAY HELPERS
# ============================================================

SEPARATOR = "=" * 70


def print_header(title: str) -> None:
    print()
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)


# ============================================================
# JSON HELPERS
# ============================================================

def load_json_file(json_path: Path) -> dict[str, Any]:
    """
    Read one processed JSON file.
    """

    with json_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def get_document_record(
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Return the document-level record from processed JSON.
    """

    document = data.get("document")

    if not isinstance(document, dict):
        raise ValueError(
            "JSON does not contain a valid 'document' object."
        )

    return document


def get_sections(
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Return section records.

    Current pipeline format stores chunks inside each section.
    """

    sections = data.get("sections", [])

    if not isinstance(sections, list):
        raise ValueError(
            "JSON 'sections' must be a list."
        )

    return [
        section
        for section in sections
        if isinstance(section, dict)
    ]


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def get_file_hash(
    document: dict[str, Any],
) -> str | None:
    """
    Return the source file hash from the processed JSON.
    """

    value = document.get("file_hash")

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def find_existing_document(
    cursor,
    file_hash: str | None,
) -> int | None:
    """
    Find an already-ingested document using FILE_HASH.

    Returns:
        DOCUMENT_ID if found
        None otherwise
    """

    if not file_hash:
        return None

    cursor.execute(
        """
        SELECT DOCUMENT_ID
        FROM DOCUMENT
        WHERE FILE_HASH = :file_hash
        """,
        file_hash=file_hash,
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return int(row[0])


# ============================================================
# SECTION HELPERS
# ============================================================

def get_section_text(
    section: dict[str, Any],
) -> str:
    """
    Extract section text from the current pipeline format.
    """

    text = section.get("text")

    if text is None:
        text = section.get("text_content")

    if text is None:
        return ""

    return str(text).strip()


def get_section_type(
    section: dict[str, Any],
) -> str:
    """
    Determine the technical section type.
    """

    section_type = section.get("section_type")

    if section_type:
        return str(section_type)

    if section.get("page_number") is not None:
        return "PAGE"

    if section.get("slide_number") is not None:
        return "SLIDE"

    return "SECTION"


def get_section_order(
    section: dict[str, Any],
    default_order: int,
) -> int:
    """
    Determine section ordering.
    """

    value = section.get("section_order")

    if value is None:
        return default_order

    try:
        return int(value)
    except (TypeError, ValueError):
        return default_order


# ============================================================
# CHUNK HELPERS
# ============================================================

def get_chunks(
    section: dict[str, Any],
) -> list[Any]:
    """
    Get chunks belonging to a section.

    Current pipeline format:
        section["chunks"]
    """

    chunks = section.get("chunks", [])

    if not isinstance(chunks, list):
        return []

    return chunks


def get_chunk_text(
    chunk: Any,
) -> str:
    """
    Extract text from either:

        "some text"

    or:

        {
            "text": "...",
            ...
        }

    or:

        {
            "chunk_text": "...",
            ...
        }
    """

    if isinstance(chunk, str):
        return chunk.strip()

    if not isinstance(chunk, dict):
        return ""

    text = chunk.get("text")

    if text is None:
        text = chunk.get("chunk_text")

    if text is None:
        return ""

    return str(text).strip()


def get_chunk_order(
    chunk: Any,
    default_order: int,
) -> int:
    """
    Determine chunk ordering.
    """

    if not isinstance(chunk, dict):
        return default_order

    value = chunk.get("chunk_order")

    if value is None:
        return default_order

    try:
        return int(value)
    except (TypeError, ValueError):
        return default_order


def get_token_count(
    chunk: Any,
    chunk_text: str,
) -> int:
    """
    Get token count supplied by the pipeline.

    If unavailable, use a simple whitespace-based estimate.
    """

    if isinstance(chunk, dict):

        value = chunk.get("token_count")

        if value is not None:

            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    return len(chunk_text.split())


# ============================================================
# INSERT DOCUMENT
# ============================================================

def insert_document(
    cursor,
    document: dict[str, Any],
) -> int:
    """
    Insert one DOCUMENT record.

    Returns:
        DOCUMENT_ID
    """

    document_id_var = cursor.var(int)

    file_hash = get_file_hash(document)

    cursor.execute(
        """
        INSERT INTO DOCUMENT (
            TITLE,
            FILE_NAME,
            FILE_TYPE,
            CLIENT_NAME,
            DESCRIPTION,
            VERSION_LABEL,
            STATUS,
            CREATED_AT,
            UPDATED_AT,
            DOCUMENT_TYPE,
            SOURCE_PATH,
            FILE_HASH,
            INGESTION_STATUS
        )
        VALUES (
            :title,
            :file_name,
            :file_type,
            :client_name,
            :description,
            :version_label,
            :status,
            SYSTIMESTAMP,
            SYSTIMESTAMP,
            :document_type,
            :source_path,
            :file_hash,
            :ingestion_status
        )
        RETURNING DOCUMENT_ID INTO :document_id
        """,
        title=document.get(
            "title",
            "Untitled Document",
        ),
        file_name=document.get(
            "file_name"
        ),
        file_type=document.get(
            "file_type"
        ),
        client_name=document.get(
            "client_name"
        ),
        description=document.get(
            "description"
        ),
        version_label=document.get(
            "version_label"
        ),
        status=document.get(
            "status",
            "ACTIVE",
        ),
        document_type=document.get(
            "document_type"
        ),
        source_path=document.get(
            "source_path"
        ),
        file_hash=file_hash,
        ingestion_status="LOADING",
        document_id=document_id_var,
    )

    document_id = document_id_var.getvalue()[0]

    return int(document_id)


# ============================================================
# INSERT SECTIONS AND CHUNKS
# ============================================================

def insert_sections_and_chunks(
    cursor,
    document_id: int,
    sections: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    Insert sections and their chunks.

    IMPORTANT:
    Empty sections are skipped because Oracle treats an empty
    string as NULL and DOCUMENT_SECTION.TEXT_CONTENT is NOT NULL.

    Returns:
        (sections_inserted, chunks_inserted)
    """

    sections_inserted = 0
    chunks_inserted = 0

    for section_index, section in enumerate(
        sections,
        start=1,
    ):

        # ----------------------------------------------------
        # Get section text
        # ----------------------------------------------------

        text_content = get_section_text(section)

        # ----------------------------------------------------
        # IMPORTANT FIX
        #
        # Some PDF pages / PPTX slides have no extractable
        # text. Oracle cannot insert NULL into TEXT_CONTENT.
        #
        # Therefore skip completely empty sections.
        # ----------------------------------------------------

        if not text_content:
            continue

        section_type = get_section_type(
            section
        )

        page_number = section.get(
            "page_number"
        )

        slide_number = section.get(
            "slide_number"
        )

        section_order = get_section_order(
            section,
            section_index,
        )

        section_title = section.get(
            "section_title"
        )

        # ----------------------------------------------------
        # Insert section
        # ----------------------------------------------------

        section_id_var = cursor.var(int)

        cursor.execute(
            """
            INSERT INTO DOCUMENT_SECTION (
                DOCUMENT_ID,
                SECTION_TYPE,
                PAGE_NUMBER,
                SLIDE_NUMBER,
                SECTION_TITLE,
                TEXT_CONTENT,
                SECTION_ORDER,
                CREATED_AT
            )
            VALUES (
                :document_id,
                :section_type,
                :page_number,
                :slide_number,
                :section_title,
                :text_content,
                :section_order,
                SYSTIMESTAMP
            )
            RETURNING SECTION_ID INTO :section_id
            """,
            document_id=document_id,
            section_type=section_type,
            page_number=page_number,
            slide_number=slide_number,
            section_title=section_title,
            text_content=text_content,
            section_order=section_order,
            section_id=section_id_var,
        )

        section_id = int(
            section_id_var.getvalue()[0]
        )

        sections_inserted += 1

        # ----------------------------------------------------
        # Insert chunks belonging to this section
        # ----------------------------------------------------

        chunks = get_chunks(section)

        for chunk_index, chunk in enumerate(
            chunks,
            start=1,
        ):

            chunk_text = get_chunk_text(
                chunk
            )

            # ------------------------------------------------
            # Skip empty chunks
            # ------------------------------------------------

            if not chunk_text:
                continue

            chunk_order = get_chunk_order(
                chunk,
                chunk_index,
            )

            token_count = get_token_count(
                chunk,
                chunk_text,
            )

            cursor.execute(
                """
                INSERT INTO DOCUMENT_CHUNK (
                    DOCUMENT_ID,
                    SECTION_ID,
                    CHUNK_TEXT,
                    CHUNK_ORDER,
                    TOKEN_COUNT,
                    CREATED_AT
                )
                VALUES (
                    :document_id,
                    :section_id,
                    :chunk_text,
                    :chunk_order,
                    :token_count,
                    SYSTIMESTAMP
                )
                """,
                document_id=document_id,
                section_id=section_id,
                chunk_text=chunk_text,
                chunk_order=chunk_order,
                token_count=token_count,
            )

            chunks_inserted += 1

    return (
        sections_inserted,
        chunks_inserted,
    )


# ============================================================
# LOAD ONE DOCUMENT
# ============================================================

def load_document(
    connection,
    json_path: Path,
) -> dict[str, Any]:
    """
    Load one processed JSON document into Oracle.

    Returns a result dictionary containing:
        status
        document_id
        sections
        chunks
        error
    """

    result = {
        "status": "FAILED",
        "document_id": None,
        "sections": 0,
        "chunks": 0,
        "error": None,
    }

    data = load_json_file(json_path)

    document = get_document_record(data)

    sections = get_sections(data)

    title = document.get(
        "title",
        json_path.stem,
    )

    print()
    print("-" * 70)
    print(f"JSON      : {json_path.name}")
    print(f"Document  : {title}")
    print(f"Sections  : {len(sections)}")

    cursor = connection.cursor()

    try:

        # ----------------------------------------------------
        # Check duplicate using FILE_HASH
        # ----------------------------------------------------

        file_hash = get_file_hash(
            document
        )

        existing_document_id = (
            find_existing_document(
                cursor,
                file_hash,
            )
        )

        if existing_document_id is not None:

            print(
                "Already in Oracle: "
                f"DOCUMENT_ID={existing_document_id}"
            )

            result["status"] = "ALREADY_EXISTS"
            result["document_id"] = (
                existing_document_id
            )

            connection.rollback()

            return result

        # ----------------------------------------------------
        # Insert DOCUMENT
        # ----------------------------------------------------

        document_id = insert_document(
            cursor,
            document,
        )

        result["document_id"] = document_id

        print(
            f"DOCUMENT inserted: "
            f"ID={document_id}"
        )

        # ----------------------------------------------------
        # Insert sections + chunks
        # ----------------------------------------------------

        (
            sections_inserted,
            chunks_inserted,
        ) = insert_sections_and_chunks(
            cursor,
            document_id,
            sections,
        )

        result["sections"] = (
            sections_inserted
        )

        result["chunks"] = (
            chunks_inserted
        )

        # ----------------------------------------------------
        # Mark document as successfully loaded
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE DOCUMENT
            SET
                INGESTION_STATUS = 'LOADED',
                STATUS = 'ACTIVE',
                UPDATED_AT = SYSTIMESTAMP
            WHERE DOCUMENT_ID = :document_id
            """,
            document_id=document_id,
        )

        # ----------------------------------------------------
        # Commit this document
        # ----------------------------------------------------

        connection.commit()

        result["status"] = "INSERTED"

        print(
            f"Sections inserted: "
            f"{sections_inserted}"
        )

        print(
            f"Chunks inserted  : "
            f"{chunks_inserted}"
        )

        print(
            "Document committed successfully."
        )

        return result

    except Exception as exc:

        # ----------------------------------------------------
        # Roll back ONLY this document
        # ----------------------------------------------------

        connection.rollback()

        result["error"] = str(exc)

        print(
            f"ERROR: {exc}"
        )

        print(
            "Transaction rolled back."
        )

        return result

    finally:

        cursor.close()


# ============================================================
# DISCOVER JSON FILES
# ============================================================

def discover_json_files() -> list[Path]:
    """
    Find all processed JSON files.
    """

    if not PROCESSED_DIR.exists():

        raise FileNotFoundError(
            "Processed directory not found:\n"
            f"{PROCESSED_DIR}"
        )

    return sorted(
        PROCESSED_DIR.glob("*.json"),
        key=lambda path: path.name.lower(),
    )


# ============================================================
# FIND DUPLICATE JSON FILES
# ============================================================

def identify_duplicate_jsons(
    json_files: list[Path],
) -> tuple[list[Path], list[Path]]:
    """
    Identify duplicate processed JSON files by FILE_HASH.

    Returns:

        unique_files
        duplicate_files

    Only the first JSON containing a given hash is retained.
    """

    unique_files: list[Path] = []
    duplicate_files: list[Path] = []

    seen_hashes: dict[str, Path] = {}

    for json_path in json_files:

        try:

            data = load_json_file(
                json_path
            )

            document = get_document_record(
                data
            )

            file_hash = get_file_hash(
                document
            )

            # ------------------------------------------------
            # No hash
            #
            # Treat as unique rather than incorrectly
            # classifying it as a duplicate.
            # ------------------------------------------------

            if not file_hash:

                unique_files.append(
                    json_path
                )

                continue

            # ------------------------------------------------
            # Duplicate hash
            # ------------------------------------------------

            if file_hash in seen_hashes:

                duplicate_files.append(
                    json_path
                )

                print(
                    "Duplicate JSON skipped:"
                )

                print(
                    f"    {json_path.name}"
                )

                continue

            # ------------------------------------------------
            # First occurrence
            # ------------------------------------------------

            seen_hashes[file_hash] = (
                json_path
            )

            unique_files.append(
                json_path
            )

        except Exception as exc:

            print(
                "WARNING: Could not inspect "
                f"{json_path.name}: {exc}"
            )

            # Keep it in the load list so the
            # actual loader reports the failure.
            unique_files.append(
                json_path
            )

    return (
        unique_files,
        duplicate_files,
    )


# ============================================================
# BATCH LOADER
# ============================================================

def load_all_documents() -> None:
    """
    Load all unique processed JSON documents into Oracle.
    """

    print_header(
        "TERRAGNI ORACLE BATCH LOADER"
    )

    print(
        f"Processed directory:\n"
        f"{PROCESSED_DIR}"
    )

    # --------------------------------------------------------
    # Discover JSON files
    # --------------------------------------------------------

    json_files = discover_json_files()

    print()
    print(
        f"JSON files found      : "
        f"{len(json_files)}"
    )

    if not json_files:

        print(
            "No JSON files found."
        )

        return

    # --------------------------------------------------------
    # Remove duplicate JSON representations
    # --------------------------------------------------------

    (
        unique_files,
        duplicate_files,
    ) = identify_duplicate_jsons(
        json_files
    )

    print()
    print(
        f"Unique documents      : "
        f"{len(unique_files)}"
    )

    print(
        f"Duplicate JSON skipped: "
        f"{len(duplicate_files)}"
    )

    # --------------------------------------------------------
    # Open Oracle connection
    # --------------------------------------------------------

    connection = get_connection()

    # --------------------------------------------------------
    # Counters
    # --------------------------------------------------------

    already_in_oracle = 0
    documents_inserted = 0

    total_sections = 0
    total_chunks = 0

    failed = 0

    try:

        total_documents = len(
            unique_files
        )

        # ----------------------------------------------------
        # Process each unique JSON
        # ----------------------------------------------------

        for index, json_path in enumerate(
            unique_files,
            start=1,
        ):

            print()
            print(
                f"[{index}/{total_documents}] "
                f"Processing: {json_path.name}"
            )

            try:

                result = load_document(
                    connection,
                    json_path,
                )

                status = result["status"]

                # --------------------------------------------
                # Already exists
                # --------------------------------------------

                if status == "ALREADY_EXISTS":

                    already_in_oracle += 1

                # --------------------------------------------
                # Successfully inserted
                # --------------------------------------------

                elif status == "INSERTED":

                    documents_inserted += 1

                    total_sections += int(
                        result["sections"]
                    )

                    total_chunks += int(
                        result["chunks"]
                    )

                # --------------------------------------------
                # Failed
                # --------------------------------------------

                else:

                    failed += 1

            except Exception as exc:

                # ------------------------------------------------
                # Safety net.
                #
                # A failure in one JSON should not stop the
                # entire batch.
                # ------------------------------------------------

                failed += 1

                try:
                    connection.rollback()
                except Exception:
                    pass

                print(
                    f"ERROR processing "
                    f"{json_path.name}: {exc}"
                )

                print(
                    "Transaction rolled back."
                )

    finally:

        connection.close()

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    print_header(
        "ORACLE INGESTION COMPLETE"
    )

    print(
        f"JSON files found       : "
        f"{len(json_files)}"
    )

    print(
        f"Unique documents       : "
        f"{len(unique_files)}"
    )

    print(
        f"Duplicate JSON skipped : "
        f"{len(duplicate_files)}"
    )

    print(
        f"Already in Oracle      : "
        f"{already_in_oracle}"
    )

    print(
        f"Documents inserted     : "
        f"{documents_inserted}"
    )

    print(
        f"Sections inserted      : "
        f"{total_sections}"
    )

    print(
        f"Chunks inserted        : "
        f"{total_chunks}"
    )

    print(
        f"Failed                 : "
        f"{failed}"
    )

    print(SEPARATOR)

    if failed == 0:

        print(
            "ALL DOCUMENTS PROCESSED "
            "SUCCESSFULLY."
        )

    else:

        print(
            f"WARNING: {failed} document(s) "
            f"failed."
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        load_all_documents()

    except Exception as exc:

        print()
        print_header(
            "ORACLE INGESTION FAILED"
        )

        print(
            f"ERROR: {exc}"
        )

        raise