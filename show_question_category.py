"""Temporary script to show where question category is stored in DB."""
import sqlite3

conn = sqlite3.connect("Diagnose_db.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(surveys_question)")
cols = cur.fetchall()
print("=== surveys_question TABLE COLUMNS ===")
for c in cols:
    print(f"  {c[1]:20} {c[2]}")

cur.execute(
    """SELECT id, "order", substr(text, 1, 50) as txt, category 
       FROM surveys_question 
       WHERE category IS NOT NULL AND category != '' 
       ORDER BY survey_type_id, "order" LIMIT 15"""
)
rows = cur.fetchall()
print("\n=== SAMPLE ROWS (id | order | category | question text) ===")
for r in rows:
    print(f"  id={r[0]:4} order={r[1]:3} category={r[3]!r:6} | {r[2]}...")

conn.close()
