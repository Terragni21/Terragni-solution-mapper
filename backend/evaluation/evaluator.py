"""
Evaluate the Terragni Solution Mapper against its success targets.

Run from the project folder:

    python -m backend.evaluation.evaluator              # everything
    python -m backend.evaluation.evaluator intent       # one area only
    python -m backend.evaluation.evaluator challenge
    python -m backend.evaluation.evaluator knowledge

Targets (from the project documentation):
    right path chosen          >= 9 out of 10
    right examples found       >= 9 out of 11
    correct Knowledge answers  >= 9 out of 10 (here: all 5 sample questions)

A JSON report is written to backend/evaluation/last_report.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from backend.evaluation.test_cases import (
    CHALLENGE_CASES,
    INTENT_CASES,
    KNOWLEDGE_CASES,
)

REPORT_PATH = Path(__file__).with_name("last_report.json")

# Groq limits tokens per minute. A short pause between AI questions keeps a
# full run under that limit. Override with EVAL_PAUSE_SECONDS=0 if you have
# a higher Groq tier.
PAUSE_SECONDS = float(os.getenv("EVAL_PAUSE_SECONDS", "8"))


def _case_codes() -> dict[int, str]:
    from backend.database.connection import get_connection

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT CASE_STUDY_ID, CASE_STUDY_CODE FROM CASE_STUDY")
        return {int(row[0]): str(row[1] or "") for row in cursor}
    finally:
        connection.close()


def evaluate_intent() -> dict:
    from backend.journey.intent import detect_intent

    rows = []
    for text, expected in INTENT_CASES:
        decision = detect_intent(text)
        rows.append(
            {
                "text": text,
                "expected": expected,
                "got": decision["intent"],
                "method": decision["method"],
                "pass": decision["intent"] == expected,
            }
        )
    return _summary("Right path chosen", rows, target_share=0.9)


def evaluate_challenge() -> dict:
    from backend.journey_service import run_journey

    codes = _case_codes()
    rows = []
    for index, (text, expected_fragments) in enumerate(CHALLENGE_CASES):
        if index:
            time.sleep(PAUSE_SECONDS)
        started = time.time()
        try:
            result = run_journey(challenge=text, industry="Banking", role="Head of Banking")
            got = [
                codes.get(int(case.get("case_study_id")), "")
                for case in result.get("case_studies", [])
                if case.get("case_study_id") is not None
            ]
            error = ""
        except Exception as exc:
            got, error = [], f"{type(exc).__name__}: {exc}"

        if expected_fragments is None:
            # Content not in the database: only an honest "no match" passes.
            passed = not got and not error
        else:
            passed = any(
                re.search(re.escape(fragment.rstrip("$")) + ("$" if fragment.endswith("$") else ""), code)
                for code in got
                for fragment in expected_fragments
            )
        rows.append(
            {
                "text": text,
                "got": got,
                "seconds": round(time.time() - started, 1),
                "error": error,
                "pass": passed,
            }
        )
    return _summary("Right examples found", rows, target_count=9)


def evaluate_knowledge() -> dict:
    from backend.journey.knowledge import answer_knowledge_question

    rows = []
    for index, (question, should_answer, keyword) in enumerate(KNOWLEDGE_CASES):
        if index:
            time.sleep(PAUSE_SECONDS)
        started = time.time()
        try:
            answer = answer_knowledge_question(question=question, industry="Banking", role="Head of Strategy")
            text = " ".join(
                [answer.get("answer", "")]
                + [item.get("name", "") for item in answer.get("offerings", [])]
            ).lower()
            passed = (
                answer["answer_found"] == should_answer
                and (not keyword or keyword in text)
            )
            got = {"answer_found": answer["answer_found"], "answer": answer.get("answer", "")[:160]}
            error = ""
        except Exception as exc:
            passed, got, error = False, {}, f"{type(exc).__name__}: {exc}"

        rows.append(
            {
                "question": question,
                "got": got,
                "seconds": round(time.time() - started, 1),
                "error": error,
                "pass": passed,
            }
        )
    return _summary("Correct answers about Terragni", rows, target_share=0.9)


def _summary(name: str, rows: list[dict], *, target_share: float | None = None, target_count: int | None = None) -> dict:
    passed = sum(1 for row in rows if row["pass"])
    total = len(rows)
    target = target_count if target_count is not None else int(round(total * (target_share or 1.0)))
    return {
        "measure": name,
        "passed": passed,
        "total": total,
        "target": f">= {target} of {total}",
        "meets_target": passed >= target,
        "rows": rows,
    }


AREAS = {
    "intent": evaluate_intent,
    "challenge": evaluate_challenge,
    "knowledge": evaluate_knowledge,
}


def main(argv: list[str]) -> int:
    wanted = argv[1:] or list(AREAS)
    report = {}

    for area in wanted:
        if area not in AREAS:
            print(f"Unknown area '{area}'. Choose from: {', '.join(AREAS)}")
            return 2
        print(f"\n=== {area} ===")
        summary = AREAS[area]()
        report[area] = summary
        for row in summary["rows"]:
            mark = "PASS" if row["pass"] else "FAIL"
            label = row.get("text") or row.get("question")
            print(f"[{mark}] {label}")
            if not row["pass"]:
                print(f"        got: {row.get('got')} {row.get('error', '')}")
        print(
            f"--> {summary['measure']}: {summary['passed']}/{summary['total']} "
            f"(target {summary['target']}) "
            f"{'MEETS TARGET' if summary['meets_target'] else 'BELOW TARGET'}"
        )

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport saved to {REPORT_PATH}")
    return 0 if all(item["meets_target"] for item in report.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
