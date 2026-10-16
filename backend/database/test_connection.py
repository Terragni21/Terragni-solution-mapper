from connection import get_connection


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    USER AS current_user,
                    SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
                    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
                FROM dual
            """)

            row = cursor.fetchone()

            print("Oracle connection successful")
            print(f"USER: {row[0]}")
            print(f"DATABASE: {row[1]}")
            print(f"SERVICE: {row[2]}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()