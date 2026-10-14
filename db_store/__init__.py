from psycopg import sql
from psycopg.types.json import Jsonb

from config import config
from db_store.connection import create_connection_pool

SIZING_SPEC_TABLE = config["postgresql_db_tables"]["sizing_spec_table"]
REQ_SPEC_TABLE = config["postgresql_db_tables"]["req_spec_table"]


class DatabaseStore:
    """Own the shared PostgreSQL pool and application-table queries."""

    def __init__(self, max_pool_size: int = 10):
        self.pool = create_connection_pool(max_pool_size)

    def save_requirement_specs(self, thread_id: str, spec: dict) -> None:
        query = sql.SQL("""
			INSERT INTO {} (thread_id, spec)
			VALUES (%s, %s)
			ON CONFLICT (thread_id) DO UPDATE
			SET spec = EXCLUDED.spec
		""").format(sql.Identifier(REQ_SPEC_TABLE))

        with self.pool.connection() as connection:
            connection.execute(query, (thread_id, Jsonb(spec)))

    def get_sizing_specs(self, thread_id: str) -> list[dict]:
        query = sql.SQL("""
			SELECT resource_category, requirement
			FROM {}
			WHERE thread_id = %s
			ORDER BY resource_category
		""").format(sql.Identifier(SIZING_SPEC_TABLE))

        with self.pool.connection() as connection:
            return connection.execute(query, (thread_id,)).fetchall()

    def save_sizing_specs(self, thread_id: str, specs: list[dict]) -> None:
        with self.pool.connection() as connection:
            for spec in specs:
                query = sql.SQL("""
					INSERT INTO {} (thread_id, resource_category, requirement)
					VALUES (%s, %s, %s)
					ON CONFLICT (thread_id, resource_category) DO UPDATE
					SET requirement = EXCLUDED.requirement
				""").format(sql.Identifier(SIZING_SPEC_TABLE))
                connection.execute(
                    query,
                    (thread_id, spec["resource_category"], Jsonb(spec["requirement"])),
                )

    def close(self) -> None:
        self.pool.close()
