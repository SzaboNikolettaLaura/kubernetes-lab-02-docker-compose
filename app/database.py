import os

from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, dsn: str | None = None) -> None:
        connection_info = dsn or make_conninfo(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )
        self._pool = ConnectionPool(
            conninfo=connection_info,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True},
            open=False,
        )

    @classmethod
    def from_environment(cls) -> "Database":
        return cls(os.getenv("DATABASE_URL") or None)

    def open(self) -> None:
        self._pool.open(wait=True, timeout=30)
        with self._pool.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL
                )
                """
            )

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> None:
        with self._pool.connection() as connection:
            connection.execute("SELECT 1")

    def list_items(self) -> list[tuple[int, str]]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT id, name FROM items ORDER BY id"
            ).fetchall()
        return [(int(item_id), str(name)) for item_id, name in rows]

    def create_item(self, name: str) -> tuple[int, str]:
        with self._pool.connection() as connection:
            row = connection.execute(
                "INSERT INTO items (name) VALUES (%s) RETURNING id, name",
                (name,),
            ).fetchone()
        if row is None:
            raise RuntimeError("item insert returned no row")
        return int(row[0]), str(row[1])

    def get_item(self, item_id: int) -> tuple[int, str] | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT id, name FROM items WHERE id = %s",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        return int(row[0]), str(row[1])

    def delete_item(self, item_id: int) -> bool:
        with self._pool.connection() as connection:
            result = connection.execute("DELETE FROM items WHERE id = %s", (item_id,))
        return result.rowcount == 1
