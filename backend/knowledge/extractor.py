from __future__ import annotations



import argparse

import json

import os

import re

from typing import Any



from dotenv import load_dotenv

from groq import Groq



from database.connection import get_connection





# ============================================================

# CONFIGURATION

# ============================================================



BACKEND_DIR = os.path.dirname(

    os.path.dirname(os.path.abspath(__file__))

)



ENV_PATH = os.path.join(

    BACKEND_DIR,

    ".env",

)



load_dotenv(ENV_PATH)





GROQ_API_KEY = os.getenv(

    "GROQ_API_KEY",

    "",

).strip()



GROQ_MODEL = os.getenv(

    "GROQ_MODEL",

    "",

).strip()





# Maximum characters from one Oracle chunk.

MAX_CHUNK_CHARS = int(

    os.getenv(

        "MAX_CHUNK_CHARS",

        "4500",

    )

)





# Maximum total source characters sent to Groq.

MAX_SOURCE_CHARS = 12000





# Maximum completion size.

MAX_COMPLETION_TOKENS = 3000





if not GROQ_API_KEY:

    raise RuntimeError(

        "GROQ_API_KEY is missing from backend/.env"

    )





if not GROQ_MODEL:

    raise RuntimeError(

        "GROQ_MODEL is missing from backend/.env"

    )





# ============================================================

# GROQ CLIENT

# ============================================================



client = Groq(

    api_key=GROQ_API_KEY

)





# ============================================================

# SYSTEM PROMPT

# ============================================================



SYSTEM_PROMPT = """

You are a knowledge extraction engine for Terragni Consulting.



Your job is to extract ONLY information that is explicitly supported

by the supplied Terragni source document chunks.



Use ONLY the supplied source chunks.



Do NOT invent:

\- case studies

\- industries

\- offerings

\- frameworks

\- challenges

\- outcomes

\- client names

\- business claims

\- relationships

\- results

\- statuses



Do NOT infer unsupported facts.



A document may contain:

\- a case study

\- an offering brochure

\- a framework description

\- an industry reference

\- multiple challenges

\- multiple outcomes

\- multiple entities



Extract only information supported by the source.



Every extracted entity MUST contain evidence.



Every evidence item MUST reference a CHUNK_ID that exists in the

supplied source chunks.



Do not use general knowledge.



If there is not enough evidence for an entity, do not create it.



Keep the output concise.



Return ONLY a valid JSON object.

"""





# ============================================================

# USER PROMPT

# ============================================================



USER_PROMPT_TEMPLATE = """

Analyze the following Terragni Consulting source document.



DOCUMENT_ID:

{document_id}



DOCUMENT_TITLE:

{document_title}



SOURCE CHUNKS:

{chunks}



Return a JSON object using exactly this structure:



{{

  "case_studies": [

    {{

      "name": "...",

      "code": null,

      "client_name": null,

      "summary": "...",

      "challenge": "...",

      "objective": "...",

      "approach": "...",

      "key_finding": "...",

      "solution": "...",

      "business_outcome": "...",

      "status": null,

      "evidence": [

        {{

          "chunk_id": 123,

          "evidence_type": "CASE_STUDY",

          "relevance_note": "...",

          "evidence_text": "Short supporting excerpt from the source."

        }}

      ]

    }}

  ],



  "industries": [

    {{

      "name": "...",

      "code": null,

      "description": "...",

      "evidence": [

        {{

          "chunk_id": 123,

          "evidence_text": "Short supporting excerpt from the source."

        }}

      ]

    }}

  ],



  "offerings": [

    {{

      "name": "...",

      "code": null,

      "description": "...",

      "evidence": [

        {{

          "chunk_id": 123,

          "evidence_text": "Short supporting excerpt from the source."

        }}

      ]

    }}

  ],



  "frameworks": [

    {{

      "name": "...",

      "code": null,

      "description": "...",

      "evidence": [

        {{

          "chunk_id": 123,

          "evidence_text": "Short supporting excerpt from the source."

        }}

      ]

    }}

  ],



  "challenges": [

    {{

      "name": "...",

      "code": null,

      "description": "...",

      "evidence": [

        {{

          "chunk_id": 123,

          "evidence_text": "Short supporting excerpt from the source."

        }}

      ]

    }}

  ],



  "outcomes": [

    {{

      "name": "...",

      "code": null,

      "description": "...",

      "evidence": [

        {{

          "chunk_id": 123,

          "evidence_text": "Short supporting excerpt from the source."

        }}

      ]

    }}

  ]

}}



IMPORTANT EXTRACTION LIMITS:



1\. Return valid JSON only.

2\. Do not use markdown.

3\. Do not add explanations before or after JSON.

4\. Do not invent missing information.

5\. Use null when a field is not explicitly supported.

6\. Every entity must have at least one evidence item.

7\. Use no more than 3 evidence items per entity.

8\. Keep every evidence_text under 300 characters.

9\. Keep descriptions concise.

10\. Keep summaries concise.

11\. Do not repeat the same evidence unnecessarily.

12\. Prefer the strongest supporting evidence.

13\. Only reference CHUNK_ID values supplied above.



IMPORTANT STATUS RULE:



Do not assign a status such as ACTIVE unless the source explicitly

states that status.



If the source does not explicitly provide a status, use null.



IMPORTANT OFFERING RULE:



Only classify something as an OFFERING if the source explicitly

presents it as a Terragni offering, service, solution, programme,

or brochure-level offering.



Do NOT classify a methodology, technique, framework, research

method, behavioural science concept, neuroscience method,

segmentation method, or analytical technique as an OFFERING

unless the source explicitly presents it as a Terragni offering.



For example, do not automatically classify:

\- Behaviour Science

\- Consumer Neuroscience

\- Experiential Segmentation

\- research methods

\- analytical techniques



as OFFERING merely because they appear in a case study.



If they are methods or frameworks rather than explicit Terragni

offerings, place them in the appropriate category only when the

source explicitly supports that classification.



IMPORTANT FRAMEWORK RULE:



Only classify something as a FRAMEWORK when the source explicitly

supports it as a framework, model, named methodology, assessment,

or structured approach.



Do not invent framework names.



IMPORTANT OUTCOME RULE:



The outcome name and description must stay faithful to the source.



Do not explain or expand an outcome using general business knowledge.



For example, if the source says:



"Increased Wallet Share"



use:



"Increased Wallet Share"



Do not create an unsupported explanation such as:



"Higher proportion of customer spend captured by the institution."



IMPORTANT CHALLENGE RULE:



The challenge must represent the business problem actually supported

by the source.



Do not infer additional problems that are not stated or clearly

supported by the evidence.



IMPORTANT EVIDENCE RULE:



Every extracted entity must be supported by the supplied source

chunks.



Do not create an entity simply because it appears plausible.



The CHUNK_ID must come from the supplied source chunks.

"""





# ============================================================

# ORACLE DOCUMENT

# ============================================================



def fetch_document(

    document_id: int,

) -> dict[str, Any] | None:



    connection = get_connection()



    cursor = None



    try:



        cursor = connection.cursor()



        cursor.execute(

            """

            SELECT

                DOCUMENT_ID,

                TITLE,

                FILE_NAME,

                DOCUMENT_TYPE,

                CLIENT_NAME,

                DESCRIPTION

            FROM DOCUMENT

            WHERE DOCUMENT_ID = :document_id

            """,

            {

                "document_id": document_id

            },

        )



        row = cursor.fetchone()



        if not row:

            return None



        columns = [

            description[0].lower()

            for description in cursor.description

        ]



        result = dict(

            zip(columns, row)

        )



        # Read CLOB while the Oracle connection

        # is still open.

        if result.get("description") is not None:



            value = result["description"]



            if hasattr(

                value,

                "read",

            ):

                result["description"] = value.read()



        return result



    finally:



        try:

            if cursor:

                cursor.close()

        except Exception:

            pass



        connection.close()





# ============================================================

# ORACLE DOCUMENT CHUNKS

# ============================================================



def fetch_document_chunks(

    document_id: int,

    limit: int | None = None,

) -> list[dict[str, Any]]:



    connection = get_connection()



    cursor = None



    try:



        cursor = connection.cursor()



        sql = """

            SELECT

                dc.CHUNK_ID,

                dc.SECTION_ID,

                dc.CHUNK_TEXT,

                ds.SECTION_TYPE,

                ds.PAGE_NUMBER,

                ds.SLIDE_NUMBER,

                ds.SECTION_TITLE,

                dc.CHUNK_ORDER

            FROM DOCUMENT_CHUNK dc

            JOIN DOCUMENT_SECTION ds

                ON ds.SECTION_ID = dc.SECTION_ID

            WHERE dc.DOCUMENT_ID = :document_id

            ORDER BY dc.CHUNK_ORDER

        """



        cursor.execute(

            sql,

            {

                "document_id": document_id

            },

        )



        rows = cursor.fetchall()



        columns = [

            description[0].lower()

            for description in cursor.description

        ]



        result = []



        for row in rows:



            item = dict(

                zip(columns, row)

            )



            # ------------------------------------------------

            # Oracle CLOB handling.

            # Read CLOBs while connection is open.

            # ------------------------------------------------



            if item.get("chunk_text") is not None:



                chunk_text = item[

                    "chunk_text"

                ]



                if hasattr(

                    chunk_text,

                    "read",

                ):

                    item["chunk_text"] = (

                        chunk_text.read()

                    )



            if item.get("section_title") is not None:



                section_title = item[

                    "section_title"

                ]



                if hasattr(

                    section_title,

                    "read",

                ):

                    item["section_title"] = (

                        section_title.read()

                    )



            result.append(item)



        if limit is not None:

            result = result[:limit]



        return result



    finally:



        try:

            if cursor:

                cursor.close()

        except Exception:

            pass



        connection.close()





# ============================================================

# TEXT CLEANING

# ============================================================



def clean_text(

    value: Any,

) -> str:



    if value is None:

        return ""



    # Handle Oracle LOB/CLOB.

    if hasattr(

        value,

        "read",

    ):



        try:

            value = value.read()

        except Exception:

            return ""



    if value is None:

        return ""



    text = str(value)



    text = text.replace(

        "\x00",

        " ",

    )



    text = re.sub(

        r"\s+",

        " ",

        text,

    )



    return text.strip()





# ============================================================

# BUILD SOURCE CONTEXT

# ============================================================



def build_chunk_context(

    chunks: list[dict[str, Any]],

) -> str:



    parts: list[str] = []



    total_chars = 0



    for chunk in chunks:



        chunk_id = chunk.get(

            "chunk_id"

        )



        section_type = clean_text(

            chunk.get(

                "section_type"

            )

        )



        page_number = chunk.get(

            "page_number"

        )



        slide_number = chunk.get(

            "slide_number"

        )



        section_title = clean_text(

            chunk.get(

                "section_title"

            )

        )



        chunk_order = chunk.get(

            "chunk_order"

        )



        chunk_text = clean_text(

            chunk.get(

                "chunk_text"

            )

        )



        if not chunk_text:

            continue



        # Limit individual chunk size.

        chunk_text = chunk_text[

            :MAX_CHUNK_CHARS

        ]



        metadata = []



        if section_type:

            metadata.append(

                f"section_type={section_type}"

            )



        if section_title:

            metadata.append(

                f"section_title={section_title}"

            )



        if page_number is not None:

            metadata.append(

                f"page={page_number}"

            )



        if slide_number is not None:

            metadata.append(

                f"slide={slide_number}"

            )



        if chunk_order is not None:

            metadata.append(

                f"chunk_order={chunk_order}"

            )



        metadata_text = ", ".join(

            metadata

        )



        source_block = (

            "--- SOURCE CHUNK ---\n"

            f"CHUNK_ID: {chunk_id}\n"

            f"{metadata_text}\n\n"

            f"TEXT:\n{chunk_text}"

        )



        # Limit total source size.

        if (

            total_chars

            + len(source_block)

            > MAX_SOURCE_CHARS

        ):

            break



        parts.append(

            source_block

        )



        total_chars += len(

            source_block

        )



    print(

        f"Source characters sent to Groq: "

        f"{total_chars}"

    )



    return "\n\n".join(parts)





# ============================================================

# GROQ EXTRACTION

# ============================================================



def extract_with_groq(

    document: dict[str, Any],

    chunks: list[dict[str, Any]],

) -> dict[str, Any]:



    chunk_context = build_chunk_context(

        chunks

    )



    if not chunk_context:



        raise RuntimeError(

            f"No usable text found for "

            f"document {document['document_id']}"

        )



    user_prompt = USER_PROMPT_TEMPLATE.format(

        document_id=document[

            "document_id"

        ],

        document_title=clean_text(

            document.get("title")

        ),

        chunks=chunk_context,

    )



    print()

    print("=" * 80)

    print("Sending document to Groq")

    print("=" * 80)



    print(

        f"Document ID : "

        f"{document['document_id']}"

    )



    print(

        f"Title       : "

        f"{document.get('title')}"

    )



    print(

        f"Chunks      : "

        f"{len(chunks)}"

    )



    print(

        f"Model       : "

        f"{GROQ_MODEL}"

    )



    print(

        f"Max source chars : "

        f"{MAX_SOURCE_CHARS}"

    )



    print(

        f"Max completion   : "

        f"{MAX_COMPLETION_TOKENS}"

    )



    request_kwargs = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        response = client.chat.completions.create(**request_kwargs)
    except Exception as exc:
        message = str(exc).lower()
        if not any(token in message for token in (
            "request too large",
            "tokens per minute",
            "rate_limit_exceeded",
        )):
            raise

        # Last-resort retry for the current Groq 8k TPM service tier.
        retry_chars = 7000
        compact_parts = []
        total = 0
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            text_value = clean_text(chunk.get("chunk_text"))[:1400]
            if not text_value:
                continue
            block = (
                f"--- SOURCE CHUNK ---\n"
                f"CHUNK_ID: {chunk_id}\n"
                f"TEXT:\n{text_value}"
            )
            if total + len(block) > retry_chars:
                break
            compact_parts.append(block)
            total += len(block)

        compact_prompt = USER_PROMPT_TEMPLATE.format(
            document_id=document["document_id"],
            document_title=clean_text(document.get("title")),
            chunks="\n\n".join(compact_parts),
        )
        request_kwargs["max_completion_tokens"] = 1800
        request_kwargs["messages"] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": compact_prompt},
        ]
        print(
            f"Groq request too large; retrying compact request "
            f"({total} source chars)."
        )
        response = client.chat.completions.create(**request_kwargs)


    content = (

        response

        .choices[0]

        .message

        .content

    )



    if not content:



        raise RuntimeError(

            "Groq returned an empty response"

        )



    return parse_json_response(

        content

    )





# ============================================================

# PARSE GROQ JSON

# ============================================================



def parse_json_response(

    content: str,

) -> dict[str, Any]:



    text = content.strip()



    # Remove accidental markdown fences.

    text = re.sub(

        r"^```(?:json)?\s*",

        "",

        text,

        flags=re.IGNORECASE,

    )



    text = re.sub(

        r"\s*```$",

        "",

        text,

        flags=re.IGNORECASE,

    )



    try:



        result = json.loads(

            text

        )



    except json.JSONDecodeError:



        start = text.find("{")

        end = text.rfind("}")



        if (

            start == -1

            or end == -1

            or end <= start

        ):



            raise RuntimeError(

                "Groq response was not valid JSON.\n\n"

                + content

            )



        try:



            result = json.loads(

                text[

                    start:end + 1

                ]

            )



        except json.JSONDecodeError as exc:



            raise RuntimeError(

                "Could not parse Groq JSON response.\n\n"

                + content

            ) from exc



    if not isinstance(

        result,

        dict,

    ):



        raise RuntimeError(

            "Groq response must be a JSON object"

        )



    return result





# ============================================================

# VALIDATION

# ============================================================



ENTITY_TYPES = [

    "case_studies",

    "industries",

    "offerings",

    "frameworks",

    "challenges",

    "outcomes",

]





def validate_extraction(

    extraction: dict[str, Any],

    source_chunk_ids: set[int],

) -> dict[str, Any]:



    validated: dict[str, Any] = {}



    for entity_type in ENTITY_TYPES:



        entities = extraction.get(

            entity_type,

            [],

        )



        if entities is None:

            entities = []



        if not isinstance(

            entities,

            list,

        ):



            raise RuntimeError(

                f"{entity_type} must be a list"

            )



        validated[

            entity_type

        ] = []



        for entity in entities:



            if not isinstance(

                entity,

                dict,

            ):

                continue



            name = clean_text(

                entity.get(

                    "name"

                )

            )



            if not name:

                continue



            evidence = entity.get(

                "evidence",

                [],

            )



            if not isinstance(

                evidence,

                list,

            ):

                evidence = []



            valid_evidence = []



            # Maximum 3 evidence records.

            for evidence_item in evidence[:3]:



                if not isinstance(

                    evidence_item,

                    dict,

                ):

                    continue



                chunk_id = (

                    evidence_item.get(

                        "chunk_id"

                    )

                )



                try:



                    chunk_id = int(

                        chunk_id

                    )



                except (

                    TypeError,

                    ValueError,

                ):

                    continue



                # Must reference a chunk actually

                # supplied to Groq.

                if (

                    chunk_id

                    not in source_chunk_ids

                ):

                    continue



                evidence_text = clean_text(

                    evidence_item.get(

                        "evidence_text"

                    )

                )



                if not evidence_text:

                    continue



                # Maximum 300 characters.

                evidence_text = (

                    evidence_text[:300]

                )



                valid_evidence.append(

                    {

                        "chunk_id": chunk_id,

                        "evidence_type": (

                            clean_text(

                                evidence_item.get(

                                    "evidence_type",

                                    "EVIDENCE",

                                )

                            )

                            or "EVIDENCE"

                        ),

                        "relevance_note": (

                            clean_text(

                                evidence_item.get(

                                    "relevance_note"

                                )

                            )

                        ),

                        "evidence_text": (

                            evidence_text

                        ),

                    }

                )



            # Discard entities without evidence.

            if not valid_evidence:

                continue



            entity_copy = dict(

                entity

            )



            entity_copy[

                "name"

            ] = name



            # Never allow the model to force ACTIVE.

            # If status is not explicitly supported,

            # it remains null.

            if entity_type == "case_studies":



                status = entity_copy.get(

                    "status"

                )



                if status not in (

                    "ACTIVE",

                    "INACTIVE",

                    "ARCHIVED",

                    "DRAFT",

                ):

                    entity_copy[

                        "status"

                    ] = None



            entity_copy[

                "evidence"

            ] = valid_evidence



            validated[

                entity_type

            ].append(

                entity_copy

            )



    return validated





# ============================================================

# INSERT STAGING RECORD

# ============================================================



def insert_staging_record(

    *,

    document_id: int,

    chunk_id: int | None,

    entity_type: str,

    entity_name: str,

    entity_code: str | None,

    relationship_type: str | None,

    extracted_text: str,

    confidence_score: float | None,

) -> None:



    connection = get_connection()



    cursor = None



    try:



        cursor = connection.cursor()



        cursor.execute(

            """

            INSERT INTO KNOWLEDGE_EXTRACTION_STAGING (

                DOCUMENT_ID,

                CHUNK_ID,

                ENTITY_TYPE,

                ENTITY_NAME,

                ENTITY_CODE,

                RELATIONSHIP_TYPE,

                EXTRACTED_TEXT,

                CONFIDENCE_SCORE,

                EXTRACTION_STATUS,

                REVIEW_NOTES

            )

            VALUES (

                :document_id,

                :chunk_id,

                :entity_type,

                :entity_name,

                :entity_code,

                :relationship_type,

                :extracted_text,

                :confidence_score,

                'PENDING',

                NULL

            )

            """,

            {

                "document_id": document_id,

                "chunk_id": chunk_id,

                "entity_type": entity_type,

                "entity_name": (

                    entity_name[:500]

                ),

                "entity_code": (

                    entity_code[:100]

                    if entity_code

                    else None

                ),

                "relationship_type": (

                    relationship_type[:100]

                    if relationship_type

                    else None

                ),

                "extracted_text": (

                    extracted_text

                ),

                "confidence_score": (

                    confidence_score

                ),

            },

        )



        connection.commit()



    except Exception:



        connection.rollback()



        raise



    finally:



        try:

            if cursor:

                cursor.close()

        except Exception:

            pass



        connection.close()





# ============================================================

# WRITE EXTRACTION TO STAGING

# ============================================================



def write_extraction_to_staging(

    document_id: int,

    extraction: dict[str, Any],

) -> int:



    inserted = 0



    entity_mapping = {

        "case_studies": "CASE_STUDY",

        "industries": "INDUSTRY",

        "offerings": "OFFERING",

        "frameworks": "FRAMEWORK",

        "challenges": "CHALLENGE",

        "outcomes": "OUTCOME",

    }



    for (

        source_key,

        entity_type,

    ) in entity_mapping.items():



        entities = extraction.get(

            source_key,

            [],

        )



        for entity in entities:



            name = clean_text(

                entity.get(

                    "name"

                )

            )



            if not name:

                continue



            code = clean_text(

                entity.get(

                    "code"

                )

            ) or None



            relationship_type = (

                clean_text(

                    entity.get(

                        "relationship_type"

                    )

                )

                or "SUPPORTING"

            )



            extracted_text = json.dumps(

                entity,

                ensure_ascii=False,

                indent=2,

            )



            confidence = entity.get(

                "confidence_score"

            )



            try:



                confidence = float(

                    confidence

                )



            except (

                TypeError,

                ValueError,

            ):



                confidence = None



            evidence = entity.get(

                "evidence",

                [],

            )



            for evidence_item in evidence:



                chunk_id = (

                    evidence_item.get(

                        "chunk_id"

                    )

                )



                evidence_text = clean_text(

                    evidence_item.get(

                        "evidence_text"

                    )

                )



                if not evidence_text:

                    continue



                insert_staging_record(

                    document_id=document_id,

                    chunk_id=chunk_id,

                    entity_type=entity_type,

                    entity_name=name,

                    entity_code=code,

                    relationship_type=(

                        relationship_type

                    ),

                    extracted_text=(

                        extracted_text

                    ),

                    confidence_score=(

                        confidence

                    ),

                )



                inserted += 1



    return inserted





# ============================================================

# CLEAR PREVIOUS PENDING RECORDS

# ============================================================



def clear_existing_pending_staging(

    document_id: int,

) -> int:



    connection = get_connection()



    cursor = None



    try:



        cursor = connection.cursor()



        cursor.execute(

            """

            DELETE FROM KNOWLEDGE_EXTRACTION_STAGING

            WHERE DOCUMENT_ID = :document_id

              AND EXTRACTION_STATUS = 'PENDING'

            """,

            {

                "document_id": document_id

            },

        )



        deleted = cursor.rowcount



        connection.commit()



        return deleted



    except Exception:



        connection.rollback()



        raise



    finally:



        try:

            if cursor:

                cursor.close()

        except Exception:

            pass



        connection.close()





# ============================================================

# EXTRACT ONE DOCUMENT

# ============================================================



def extract_document(

    document_id: int,

    *,

    chunk_limit: int | None = None,

    clear_pending: bool = True,

) -> dict[str, Any]:



    # --------------------------------------------------------

    # Load document

    # --------------------------------------------------------



    document = fetch_document(

        document_id

    )



    if not document:



        raise ValueError(

            f"Document {document_id} does not exist"

        )



    print()

    print("=" * 80)

    print("Loading document from Oracle")

    print("=" * 80)



    print(

        f"Document ID : {document_id}"

    )



    print(

        f"Title       : "

        f"{document.get('title')}"

    )



    # --------------------------------------------------------

    # Load chunks

    # --------------------------------------------------------



    chunks = fetch_document_chunks(

        document_id,

        limit=chunk_limit,

    )



    if not chunks:



        raise ValueError(

            f"Document {document_id} has no chunks"

        )



    source_chunk_ids = {

        int(chunk["chunk_id"])

        for chunk in chunks

        if chunk.get(

            "chunk_id"

        ) is not None

    }



    print(

        f"Chunks loaded: {len(chunks)}"

    )



    # --------------------------------------------------------

    # Groq extraction

    # --------------------------------------------------------



    extraction = extract_with_groq(

        document,

        chunks,

    )



    # --------------------------------------------------------

    # Validate

    # --------------------------------------------------------



    validated = validate_extraction(

        extraction,

        source_chunk_ids,

    )



    # --------------------------------------------------------

    # Remove previous PENDING rows

    # --------------------------------------------------------



    if clear_pending:



        deleted = (

            clear_existing_pending_staging(

                document_id

            )

        )



    else:



        deleted = 0



    # --------------------------------------------------------

    # Write to staging

    # --------------------------------------------------------



    inserted = (

        write_extraction_to_staging(

            document_id,

            validated,

        )

    )



    # --------------------------------------------------------

    # Summary

    # --------------------------------------------------------



    summary = {

        "document_id": document_id,

        "document_title": document.get(

            "title"

        ),

        "chunks_sent": len(chunks),

        "previous_pending_deleted": (

            deleted

        ),

        "staging_rows_inserted": (

            inserted

        ),

        "case_studies": len(

            validated[

                "case_studies"

            ]

        ),

        "industries": len(

            validated[

                "industries"

            ]

        ),

        "offerings": len(

            validated[

                "offerings"

            ]

        ),

        "frameworks": len(

            validated[

                "frameworks"

            ]

        ),

        "challenges": len(

            validated[

                "challenges"

            ]

        ),

        "outcomes": len(

            validated[

                "outcomes"

            ]

        ),

    }



    return summary





# ============================================================

# COMMAND LINE

# ============================================================



def main() -> None:



    parser = argparse.ArgumentParser(

        description=(

            "Extract Terragni knowledge from "

            "Oracle document chunks using Groq."

        )

    )



    parser.add_argument(

        "document_id",

        type=int,

        help=(

            "Oracle DOCUMENT_ID to process"

        ),

    )



    parser.add_argument(

        "--chunk-limit",

        type=int,

        default=None,

        help=(

            "Maximum number of chunks to "

            "send to Groq."

        ),

    )



    parser.add_argument(

        "--keep-pending",

        action="store_true",

        help=(

            "Keep previous PENDING staging "

            "records for this document."

        ),

    )



    args = parser.parse_args()



    summary = extract_document(

        args.document_id,

        chunk_limit=args.chunk_limit,

        clear_pending=(

            not args.keep_pending

        ),

    )



    print()

    print("=" * 80)

    print("EXTRACTION COMPLETE")

    print("=" * 80)



    for key, value in summary.items():



        print(

            f"{key:35}: {value}"

        )





if __name__ == "__main__":

    main()