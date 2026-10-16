from database.connection import get_connection

c = get_connection()
cur = c.cursor()

cur.execute("""
    SELECT CASE_STUDY_ID, TITLE
    FROM CASE_STUDY
    ORDER BY CASE_STUDY_ID
""")

rows = cur.fetchall()

print("CASE STUDY COUNT:", len(rows))

for row in rows:
    print(row)

cur.close()
c.close()
