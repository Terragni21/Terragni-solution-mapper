from database.connection import get_connection

c = get_connection()
cur = c.cursor()

cur.execute("""
    SELECT
        e.CASE_STUDY_ID,
        e.CHUNK_ID,
        d.DOCUMENT_ID,
        d.TITLE,
        s.SECTION_TITLE
    FROM CASE_STUDY_EVIDENCE e
    JOIN DOCUMENT_CHUNK ch
        ON ch.CHUNK_ID = e.CHUNK_ID
    JOIN DOCUMENT_SECTION s
        ON s.SECTION_ID = ch.SECTION_ID
    JOIN DOCUMENT d
        ON d.DOCUMENT_ID = s.DOCUMENT_ID
    WHERE e.CASE_STUDY_ID IN (3, 21)
    ORDER BY e.CASE_STUDY_ID, d.DOCUMENT_ID, e.CHUNK_ID
""")

for row in cur.fetchall():
    print(row)

cur.close()
c.close()
