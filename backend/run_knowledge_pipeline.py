from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from database.connection import get_connection


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "knowledge_pipeline_logs"
LOG_DIR.mkdir(exist_ok=True)


def get_documents():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DOCUMENT_ID, TITLE
        FROM DOCUMENT
        ORDER BY DOCUMENT_ID
    """)
    documents = cur.fetchall()

    cur.execute("""
        SELECT
            DOCUMENT_ID,
            UPPER(NVL(EXTRACTION_STATUS, 'PENDING')) AS EXTRACTION_STATUS,
            COUNT(*) AS CNT
        FROM KNOWLEDGE_EXTRACTION_STAGING
        GROUP BY DOCUMENT_ID, UPPER(NVL(EXTRACTION_STATUS, 'PENDING'))
    """)
    status_rows = cur.fetchall()

    cur.close()
    conn.close()

    statuses = {}
    for document_id, status, count in status_rows:
        statuses.setdefault(document_id, {})[status] = count

    return documents, statuses


def run_module(module: str, args: list[str], log_path: Path) -> int:
    command = [sys.executable, "-m", module, *args]

    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n" + "=" * 100 + "\n")
        log.write(
            f"{datetime.now().isoformat(timespec='seconds')} | "
            f"{' '.join(command)}\n"
        )
        log.write("=" * 100 + "\n")

        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    return result.returncode


def main():
    documents, statuses = get_documents()

    print("=" * 70)
    print("Terragni Knowledge Pipeline")
    print("=" * 70)
    print(f"Documents found: {len(documents)}")
    print()

    summary = []

    for document_id, title in documents:
        doc_status = statuses.get(document_id, {})

        pending = doc_status.get("PENDING", 0)
        promoted = doc_status.get("PROMOTED", 0)
        failed = doc_status.get("FAILED", 0)
        rejected = doc_status.get("REJECTED", 0)
        total_staging = sum(doc_status.values())

        safe_title = (title or "").replace("\n", " ").strip()
        print(f"[{document_id}] {safe_title}")
        print(f"    staging={total_staging} pending={pending} promoted={promoted}")

        # Already fully promoted: leave it alone.
        if total_staging and not pending and not failed and not rejected:
            print("    -> SKIP: already promoted")
            summary.append((document_id, "SKIPPED_ALREADY_PROMOTED"))
            continue

        # Existing pending extraction: promote it first.
        if pending and not failed and not rejected:
            print("    -> PROMOTE: existing pending staging")
            log_path = LOG_DIR / f"document_{document_id}_promote.log"
            rc = run_module(
                "knowledge.promoter",
                ["--document-id", str(document_id)],
                log_path,
            )
            if rc == 0:
                print("    -> OK")
                summary.append((document_id, "PROMOTED_EXISTING_STAGING"))
            else:
                print(f"    -> ERROR: promoter exit code {rc}")
                summary.append((document_id, f"PROMOTER_FAILED_{rc}"))
            continue

        # No staging, or failed/rejected extraction: extract fresh, then promote.
        print("    -> EXTRACT")
        extract_log = LOG_DIR / f"document_{document_id}_extract.log"
        rc = run_module(
            "knowledge.extractor",
            [str(document_id)],
            extract_log,
        )

        if rc != 0:
            print(f"    -> ERROR: extractor exit code {rc}")
            summary.append((document_id, f"EXTRACTOR_FAILED_{rc}"))
            continue

        print("    -> PROMOTE")
        promote_log = LOG_DIR / f"document_{document_id}_promote.log"
        rc = run_module(
            "knowledge.promoter",
            ["--document-id", str(document_id)],
            promote_log,
        )

        if rc == 0:
            print("    -> OK")
            summary.append((document_id, "EXTRACTED_AND_PROMOTED"))
        else:
            print(f"    -> ERROR: promoter exit code {rc}")
            summary.append((document_id, f"PROMOTER_FAILED_{rc}"))

    print()
    print("=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)

    counts = {}
    for _, status in summary:
        counts[status] = counts.get(status, 0) + 1

    for status, count in sorted(counts.items()):
        print(f"{status:35} {count}")

    print()
    print(f"Logs: {LOG_DIR}")


if __name__ == "__main__":
    main()
