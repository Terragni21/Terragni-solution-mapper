from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def extract_pdf(path: str | Path) -> list[dict]:
    """
    Extract a PDF page-by-page.

    Returns:
        [
            {
                "page_number": 1,
                "text": "...",
            },
            ...
        ]
    """

    pdf_path = Path(path)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF file not found: {pdf_path}"
        )

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"Expected a PDF file, got: {pdf_path.suffix}"
        )

    reader = PdfReader(str(pdf_path))

    sections: list[dict] = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        text = page.extract_text() or ""

        text = text.strip()

        sections.append(
            {
                "page_number": page_number,
                "text": text,
            }
        )

    return sections