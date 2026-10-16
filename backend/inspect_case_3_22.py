from database.connection import get_connection

c = get_connection()
cur = c.cursor()

cur.execute("""
    SELECT
        CASE_STUDY_ID,
        TITLE,
        SUMMARY,
        CHALLENGE,
        OBJECTIVE,
        APPROACH,
        KEY_FINDING,
        SOLUTION,
        BUSINESS_OUTCOME
    FROM CASE_STUDY
    WHERE CASE_STUDY_ID IN (3, 22)
    ORDER BY CASE_STUDY_ID
""")

for row in cur.fetchall():
    print("\n" + "=" * 100)
    print("CASE_STUDY_ID:", row[0])
    print("TITLE:", row[1])
    print("SUMMARY:", row[2])
    print("CHALLENGE:", row[3])
    print("OBJECTIVE:", row[4])
    print("APPROACH:", row[5])
    print("KEY_FINDING:", row[6])
    print("SOLUTION:", row[7])
    print("BUSINESS_OUTCOME:", row[8])

cur.close()
c.close()
