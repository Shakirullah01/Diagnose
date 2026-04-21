"""
Export survey system data from the current DB (typically SQLite) into CSV files
under data/system/ for use with import_survey_data / load_system_survey_data.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "system"


def main() -> None:
    db_path = ROOT / "Diagnose_db.db"
    if not db_path.is_file():
        raise SystemExit(f"Expected SQLite at {db_path}")
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)

    def export_questions(slug: str, filename: str, fieldnames: list[str], row_fn) -> None:
        sql = """
        SELECT q."order", q.text, q.category, q.age_min_months, q.age_max_months
        FROM surveys_question q
        JOIN surveys_surveytype t ON q.survey_type_id = t.id
        WHERE t.slug = ?
        ORDER BY q."order", q.id
        """
        rows = con.execute(sql, (slug,)).fetchall()
        path = OUT / filename
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for order, text, category, amin, amax in rows:
                w.writerow(row_fn(order, text, category, amin, amax))
        print(f"{slug}: {len(rows)} -> {path.relative_to(ROOT)}")

    # KID import expects: order, question, category_y / category_x
    export_questions(
        "kdi",
        "kid_questions_with_categories.csv",
        ["order", "question", "category_y", "category_x"],
        lambda order, text, cat, _a, _b: {
            "order": order,
            "question": text or "",
            "category_y": (cat or "").strip().upper(),
            "category_x": "",
        },
    )

    export_questions(
        "rcdi",
        "rcdi_questions_with_categories.csv",
        ["order", "question", "category"],
        lambda order, text, cat, _a, _b: {
            "order": order,
            "question": text or "",
            "category": (cat or "").strip().upper(),
        },
    )

    # M-CHAT / EJS: dedicated CSV loaders use these filenames
    export_questions(
        "m-chat",
        "mchat_questions.csv",
        ["question_order", "question"],
        lambda order, text, _c, _a, _b: {"question_order": order, "question": text or ""},
    )

    export_questions(
        "ezhs",
        "ejs_questions.csv",
        ["question_order", "question", "age", "topic"],
        lambda order, text, cat, amin, _b: {
            "question_order": order,
            "question": text or "",
            "age": "" if amin is None else str(int(amin)),
            "topic": (cat or "").strip(),
        },
    )

    # Norms
    kid_rows = con.execute(
        'SELECT age_months, category, "normal", warning, low FROM surveys_kidnorm ORDER BY age_months, category'
    ).fetchall()
    with (OUT / "kid_norms.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["age_months", "area", "normal", "warning", "low"])
        w.writeheader()
        for age, cat, normal, warning, low in kid_rows:
            w.writerow(
                {
                    "age_months": age,
                    "area": cat,
                    "normal": normal,
                    "warning": warning,
                    "low": low,
                }
            )
    print(f"kid_norms: {len(kid_rows)} -> data/system/kid_norms.csv")

    rcdi_rows = con.execute(
        'SELECT age_months, sex, category, "normal", warning, low FROM surveys_rcdinorm ORDER BY age_months, sex, category'
    ).fetchall()
    with (OUT / "rcdi_norms.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["age_months", "sex", "area", "normal", "warning", "low"])
        w.writeheader()
        for age, sex, cat, normal, warning, low in rcdi_rows:
            w.writerow(
                {
                    "age_months": age,
                    "sex": sex,
                    "area": cat,
                    "normal": normal,
                    "warning": warning,
                    "low": low,
                }
            )
    print(f"rcdi_norms: {len(rcdi_rows)} -> data/system/rcdi_norms.csv")

    con.close()


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    main()
