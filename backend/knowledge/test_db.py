from knowledge.db import fetch_one


result = fetch_one("""
    SELECT
        COUNT(*) AS TOTAL_DOCUMENTS
    FROM DOCUMENT
""")

print(result)