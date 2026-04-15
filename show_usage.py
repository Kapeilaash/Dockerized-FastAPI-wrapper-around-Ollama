import sqlite3


def main() -> None:
    conn = sqlite3.connect("usage.db", timeout=10)
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print("tables:", tables)

        rows = conn.execute(
            "SELECT ts_utc, method, path, status_code, duration_ms, model, error_type "
            "FROM request_logs ORDER BY id DESC LIMIT 20"
        ).fetchall()
        print("latest_rows:", rows)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

