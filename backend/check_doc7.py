from database.connection import get_connection

c = get_connection()
cur = c.cursor()

cur.execute("""
    SELECT COUNT(*)
    FROM DOCUMENT_CHUNK
    WHERE DOCUMENT_ID = 7
""")

print("Document 7 chunks:", cur.fetchone()[0])

cur.execute("""
    SELECT COUNT(*)
    FROM KNOWLEDGE_EXTRACTION_STAGING
    WHERE DOCUMENT_ID = 7
""")

print("Document 7 staging rows:", cur.fetchone()[0])

cur.close()
c.close()
