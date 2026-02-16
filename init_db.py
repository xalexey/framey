"""Initialize the database and create a test user."""

from app.database import create_tables, get_connection


def main():
    create_tables()

    conn = get_connection()

    existing = conn.execute("SELECT id FROM users WHERE api_key = ?", ("test-key",)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (api_key, name) VALUES (?, ?)",
            ("test-key", "Test User"),
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO user_settings (user_id) VALUES (?)",
            (user_id,),
        )
        conn.commit()
        print(f"Created test user (id={user_id}) with API key: test-key")
    else:
        print("Test user already exists")

    conn.close()


if __name__ == "__main__":
    main()
