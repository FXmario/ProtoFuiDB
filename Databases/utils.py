import sqlite3
from typing import Any

import sqlglot
from sqlglot.errors import ParseError

from .crypto import decrypt
from .models import Database


class UnsupportedProviderError(Exception):
    """Raised when a provider cannot be introspected or queried live."""


class DatabaseQueryError(Exception):
    """Raised when a query fails or refers to an invalid object."""


def check_db_connection(provider, db_name, user, password, host, port, file_path=None):
    """Validate that connection details work. Used by the create form."""
    try:
        if provider == Database.POSTGRESQL:
            import psycopg2

            conn = psycopg2.connect(
                dbname=db_name,
                user=user,
                password=password,
                host=host,
                port=int(port) if port else 5432,
            )
            conn.close()
        elif provider == Database.MARIADB_MYSQL:
            import MySQLdb

            conn = MySQLdb.connect(
                db=db_name,
                user=user,
                passwd=password,
                host=host,
                port=int(port) if port else 3306,
            )
            conn.close()
        elif provider == Database.SQLITE3:
            if not file_path:
                return False, "No database file provided for SQLite3."
            conn = sqlite3.connect(file_path)
            conn.close()
        else:
            return False, f"Unsupported provider: {provider}"
    except Exception as e:
        if provider == Database.POSTGRESQL:
            return False, f"PostgreSQL connection failed: {e}"
        elif provider == Database.MARIADB_MYSQL:
            return False, f"MariaDB/MySQL connection failed: {e}"
        elif provider == Database.SQLITE3:
            return False, f"SQLite3 connection failed: {e}"
        return False, f"Connection failed: {e}"

    provider_label = dict(Database.PROVIDER_CHOICES).get(provider, provider)
    return True, f"Successfully connected to {provider_label}."


def sqlglot_dialect(provider: str) -> str:
    return Database.SQLGLOT_DIALECTS.get(provider, "sqlite")


def open_connection(database: Database):
    """Open a live connection for introspection and querying."""
    try:
        if database.provider == Database.SQLITE3:
            if not database.file:
                raise DatabaseQueryError("No database file uploaded for SQLite3.")
            return sqlite3.connect(database.file.path)

        if database.provider == Database.POSTGRESQL:
            import psycopg2

            return psycopg2.connect(
                dbname=database.db_name,
                user=database.user,
                password=decrypt(database.password),
                host=database.host,
                port=int(database.port) if database.port else 5432,
            )

        if database.provider == Database.MARIADB_MYSQL:
            import MySQLdb

            return MySQLdb.connect(
                db=database.db_name,
                user=database.user,
                passwd=decrypt(database.password),
                host=database.host,
                port=int(database.port) if database.port else 3306,
            )

        raise UnsupportedProviderError(f"Unsupported provider: {database.provider}")
    except (DatabaseQueryError, UnsupportedProviderError):
        raise
    except Exception as e:
        raise DatabaseQueryError(f"Could not connect to database: {e}") from e


def _validate_table_name(database: Database, table_name: str, tables: list[str] | None = None) -> str:
    if tables is None:
        tables = list_tables(database)
    if table_name not in tables:
        raise DatabaseQueryError(f"Table {table_name!r} does not exist.")
    return table_name


def _quote_sqlite_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_mysql_identifier(name: str) -> str:
    return '`' + name.replace('`', '``') + '`'


def list_tables(database: Database) -> list[str]:
    """Return a sorted list of user table names for the database."""
    conn = open_connection(database)
    try:
        cursor = conn.cursor()
        if database.provider == Database.POSTGRESQL:
            cursor.execute(
                """
                SELECT tablename FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            return sorted([row[0] for row in cursor.fetchall()])

        if database.provider == Database.MARIADB_MYSQL:
            cursor.execute("SHOW TABLES")
            return sorted([row[0] for row in cursor.fetchall()])

        if database.provider == Database.SQLITE3:
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%%'
                ORDER BY name
                """
            )
            return [row[0] for row in cursor.fetchall()]

        raise UnsupportedProviderError("Listing tables is not supported for this provider.")
    finally:
        conn.close()


def get_columns(database: Database, table_name: str) -> list[tuple[str, str]]:
    """Return [(column_name, data_type), ...] for a validated table."""
    tables = list_tables(database)
    _validate_table_name(database, table_name, tables)

    conn = open_connection(database)
    try:
        cursor = conn.cursor()
        if database.provider == Database.POSTGRESQL:
            cursor.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]

        if database.provider == Database.MARIADB_MYSQL:
            cursor.execute(f"SHOW COLUMNS FROM {_quote_mysql_identifier(table_name)}")
            return [(row[0], row[1]) for row in cursor.fetchall()]

        if database.provider == Database.SQLITE3:
            cursor.execute(f'PRAGMA table_info({_quote_sqlite_identifier(table_name)})')
            return [(row[1], row[2]) for row in cursor.fetchall()]

        raise UnsupportedProviderError("Reading columns is not supported for this provider.")
    finally:
        conn.close()


def run_query(database: Database, query: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Execute arbitrary SQL and return (columns, rows).

    For result-set queries, columns are read from cursor.description.
    For DDL/DML, a single-row result [('Rows affected',), (rowcount,)] is returned.
    """
    conn = open_connection(database)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return columns, rows

        rowcount = cursor.rowcount if cursor.rowcount is not None else -1
        conn.commit()
        return ["Rows affected"], [(rowcount,)]
    except Exception as e:
        conn.rollback()
        raise DatabaseQueryError(str(e)) from e
    finally:
        conn.close()


def lint_sql(query: str, provider: str) -> list[dict[str, Any]]:
    """Return a list of syntax diagnostics for the given SQL query."""
    dialect = sqlglot_dialect(provider)
    try:
        sqlglot.parse_one(query, dialect=dialect)
    except ParseError as e:
        diagnostics = []
        for err in e.errors:
            diagnostics.append(
                {
                    "line": err.get("line") or 1,
                    "col": err.get("col") or 1,
                    "message": err.get("description") or str(e),
                }
            )
        return diagnostics
    return []
