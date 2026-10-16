from database.connection import get_connection

c = get_connection()
cur = c.cursor()

cur.execute("""
    SELECT CASE_STUDY_ID, CASE_STUDY_CODE, TITLE
    FROM CASE_STUDY
    ORDER BY CASE_STUDY_ID
""")

for row in cur.fetchall():
    print(row)

cur.close()
c.close()
