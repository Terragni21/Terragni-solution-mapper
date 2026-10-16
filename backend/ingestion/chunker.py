from __future__ import annotations

import re
import unicodedata


# ============================================================
# Text normalization
# ============================================================

def normalize_text(text: str) -> str:
    """
    Conservatively normalize extracted PDF/PPTX/DOCX text.

    This function does not attempt to rewrite business meaning.
    """

    if not text:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = text.replace(
        "\r\n",
        "\n",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    # Remove non-printing control characters.
    text = "".join(
        character
        for character in text
        if character in ("\n", "\t")
        or character.isprintable()
    )

    # Join words broken by a hyphen at a line break.
    #
    # Example:
    #
    # customer-
    # experience
    #
    # becomes:
    #
    # customerexperience
    #
    # This is preferable to preserving an artificial
    # PDF line-break hyphen.
    text = re.sub(
        r"(?<=\w)-\n(?=\w)",
        "",
        text,
    )

    # Tabs -> spaces
    text = text.replace(
        "\t",
        " ",
    )

    # Excessive spaces
    text = re.sub(
        r"[ ]{2,}",
        " ",
        text,
    )

    # Remove spaces immediately following a newline
    text = re.sub(
        r"\n[ ]+",
        "\n",
        text,
    )

    # Excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# ============================================================
# Remove known repeated document noise
# ============================================================

def remove_common_noise(text: str) -> str:
    """
    Remove repeated Terragni confidentiality/footer text.

    This is deliberately limited to clearly identifiable
    repeated document metadata. It does not attempt to
    interpret or rewrite business content.
    """

    if not text:
        return ""

    lines = text.splitlines()

    cleaned_lines: list[str] = []

    for line in lines:

        original_line = line.strip()

        if not original_line:
            cleaned_lines.append("")
            continue

        normalized_line = re.sub(
            r"\s+",
            " ",
            original_line,
        ).strip()

        lower_line = (
            normalized_line
            .lower()
        )

        # ----------------------------------------------------
        # Terragni confidentiality footer
        #
        # Handles variations such as:
        #
        # @ Terragni consulting (P) ltd Private and confidential
        # Terragni consulting (P) Ltd Private and confidential
        # © Terragni consulting (P) ltd Private and confidential
        # ----------------------------------------------------

        if (
            "terragni consulting" in lower_line
            and "private and confidential" in lower_line
        ):
            continue

        # ----------------------------------------------------
        # Circulation restriction
        # ----------------------------------------------------

        if (
            "not to be circulated" in lower_line
            and "prior authorisation" in lower_line
        ):
            continue

        if (
            "not to be circulated" in lower_line
            and "prior authorization" in lower_line
        ):
            continue

        cleaned_lines.append(
            normalized_line
        )

    text = "\n".join(
        cleaned_lines
    )

    # --------------------------------------------------------
    # Sometimes PDF extraction combines footer text with
    # adjacent text on one line.
    #
    # Remove the identifiable footer phrase without touching
    # the rest of the line.
    # --------------------------------------------------------

    text = re.sub(
        r"[@©]?\s*Terragni\s+consulting\s+\(P\)\s+ltd\s+Private\s+and\s+confidential",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"Not\s+to\s+be\s+circulated\s+without\s+prior\s+authori[sz]ation",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Clean up whitespace created by removals
    # --------------------------------------------------------

    text = re.sub(
        r"[ ]{2,}",
        " ",
        text,
    )

    text = re.sub(
        r"\n[ ]+",
        "\n",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# ============================================================
# Complete cleaning pipeline
# ============================================================

def clean_text(text: str) -> str:
    """
    Apply the complete conservative cleaning pipeline.
    """

    text = normalize_text(
        text
    )

    text = remove_common_noise(
        text
    )

    return text.strip()


# ============================================================
# Chunking
# ============================================================

def split_text(
    text: str,
    max_chars: int = 4500,
    overlap_chars: int = 500,
) -> list[str]:
    """
    Split cleaned text into overlapping chunks.

    Priority:

        paragraphs
        sentences
        character boundaries

    Chunks are kept within max_chars where possible.
    """

    text = clean_text(
        text
    )

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    paragraphs = [
        paragraph.strip()
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]

    chunks: list[str] = []

    current = ""

    # ========================================================
    # Paragraph-level packing
    # ========================================================

    for paragraph in paragraphs:

        if len(paragraph) <= max_chars:

            candidate = (
                f"{current}\n\n{paragraph}"
                if current
                else paragraph
            )

            if len(candidate) <= max_chars:

                current = candidate
                continue

            if current:
                chunks.append(
                    current
                )

            current = paragraph

            continue

        # ----------------------------------------------------
        # Paragraph is larger than max_chars
        # ----------------------------------------------------

        if current:

            chunks.append(
                current
            )

            current = ""

        # ----------------------------------------------------
        # Sentence-level splitting
        # ----------------------------------------------------

        sentences = re.split(
            r"(?<=[.!?])\s+",
            paragraph,
        )

        sentence_buffer = ""

        for sentence in sentences:

            sentence = sentence.strip()

            if not sentence:
                continue

            candidate = (
                f"{sentence_buffer} {sentence}"
                if sentence_buffer
                else sentence
            )

            if len(candidate) <= max_chars:

                sentence_buffer = candidate
                continue

            if sentence_buffer:

                chunks.append(
                    sentence_buffer
                )

            # ------------------------------------------------
            # Sentence itself is too large
            # ------------------------------------------------

            if len(sentence) > max_chars:

                start = 0

                while start < len(sentence):

                    end = min(
                        start + max_chars,
                        len(sentence),
                    )

                    piece = sentence[
                        start:end
                    ].strip()

                    if piece:
                        chunks.append(
                            piece
                        )

                    if end >= len(sentence):
                        break

                    start = max(
                        end - overlap_chars,
                        start + 1,
                    )

                sentence_buffer = ""

            else:

                sentence_buffer = sentence

        if sentence_buffer:

            current = sentence_buffer

    if current:

        chunks.append(
            current
        )

    # ========================================================
    # Overlap adjacent chunks
    # ========================================================

    if (
        overlap_chars <= 0
        or len(chunks) <= 1
    ):
        return chunks

    overlapped: list[str] = []

    for index, chunk in enumerate(
        chunks
    ):

        if index == 0:

            overlapped.append(
                chunk
            )

            continue

        previous = chunks[
            index - 1
        ]

        overlap = previous[
            -overlap_chars:
        ].strip()

        if overlap:

            combined = (
                f"{overlap}\n\n{chunk}"
            )

        else:

            combined = chunk

        if len(combined) > max_chars:

            combined = combined[
                -max_chars:
            ]

        overlapped.append(
            combined
        )

    return overlapped