from database.connection import get_connection

c = get_connection()
cur = c.cursor()

cur.execute("""
    SELECT
        STAGING_ID,
        DOCUMENT_ID,
        CHUNK_ID,
        ENTITY_NAME,
        ENTITY_CODE,
        EXTRACTED_TEXT
    FROM KNOWLEDGE_EXTRACTION_STAGING
    WHERE DOCUMENT_ID IN (5, 6)
      AND ENTITY_TYPE = 'CASE_STUDY'
    ORDER BY DOCUMENT_ID, STAGING_ID
""")

for row in cur.fetchall():
    print("\n" + "=" * 100)
    print("STAGING_ID :", row[0])
    print("DOCUMENT_ID:", row[1])
    print("CHUNK_ID   :", row[2])
    print("ENTITY_NAME:", row[3])
    print("ENTITY_CODE:", row[4])
    print("EXTRACTED_TEXT:")
    print(row[5])

cur.close()
c.close()
