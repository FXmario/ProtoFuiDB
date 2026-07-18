"""Export/import helpers for Database instances."""
import json
import os
import shutil
import sqlite3
import subprocess
from typing import Any

from .crypto import decrypt
from .models import Database
from .utils import get_columns, list_tables, quote_identifier, run_query


class DatabaseExportError(Exception):
    """Raised when exporting a database fails."""


class DatabaseImportError(Exception):
    """Raised when importing a database file fails."""


def _ensure_binary(name: str) -> str:
    if shutil.which(name) is None:
        raise DatabaseExportError(
            f"Required command-line tool {name!r} is not installed on the server."
        )
    return name


def export_sql(database: Database) -> str:
    """Return a .sql dump of the database using native CLI tools."""
    provider = database.provider
    try:
        if provider == Database.SQLITE3:
            if not database.file:
                raise DatabaseExportError("No database file uploaded for SQLite3.")
            sqlite3_bin = _ensure_binary("sqlite3")
            result = subprocess.run(
                [sqlite3_bin, database.file.path, ".dump"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise DatabaseExportError(
                    f"sqlite3 dump failed: {result.stderr.strip() or 'unknown error'}"
                )
            return result.stdout

        if provider == Database.POSTGRESQL:
            _ensure_binary("pg_dump")
            env = os.environ.copy()
            if database.password:
                env["PGPASSWORD"] = decrypt(database.password)
            cmd = [
                "pg_dump",
                "--host", database.host or "localhost",
                "--port", str(database.port or 5432),
                "--username", database.user or "",
                "--dbname", database.db_name,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=env, check=False
            )
            if result.returncode != 0:
                raise DatabaseExportError(
                    f"pg_dump failed: {result.stderr.strip() or 'unknown error'}"
                )
            return result.stdout

        if provider == Database.MARIADB_MYSQL:
            _ensure_binary("mysqldump")
            password = decrypt(database.password) if database.password else ""
            cmd = [
                "mysqldump",
                "--host", database.host or "localhost",
                "--port", str(database.port or 3306),
                "--user", database.user or "",
                f"--password={password}",
                database.db_name,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                raise DatabaseExportError(
                    f"mysqldump failed: {result.stderr.strip() or 'unknown error'}"
                )
            return result.stdout

        raise DatabaseExportError(f"Unsupported provider for SQL export: {provider}")
    except DatabaseExportError:
        raise
    except Exception as e:
        raise DatabaseExportError(f"SQL export failed: {e}") from e


def export_json(database: Database) -> dict[str, Any]:
    """Return a JSON-serializable dict describing every table in the database."""
    payload: dict[str, Any] = {
        "database": database.name,
        "provider": database.provider,
        "tables": [],
    }
    tables = list_tables(database)
    for table in tables:
        columns = get_columns(database, table)
        col_names = [c[0] for c in columns]
        _, rows = run_query(database, f"SELECT * FROM {quote_identifier(database, table)}")
        serialised_rows = []
        for row in rows:
            serialised_rows.append([
                _json_safe(cell) for cell in row
            ])
        payload["tables"].append({
            "name": table,
            "columns": [{"name": n, "type": t} for n, t in columns],
            "rows": serialised_rows,
        })
    return payload


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1", errors="replace")
    return value


def import_sqlite_from_sql(db_path: str, sql_text: str) -> None:
    """Build a fresh SQLite database at db_path by executing sql_text."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql_text)
        conn.commit()
    except sqlite3.Error as e:
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)
        raise DatabaseImportError(f"Could not execute SQL script: {e}") from e
    conn.close()


def import_sqlite_from_json(db_path: str, payload: dict[str, Any]) -> None:
    """Build a fresh SQLite database at db_path from a JSON payload.

    The payload shape is {"tables": [{"name", "columns": [{"name","type"}], "rows": [...]}]}.
    """
    if not isinstance(payload, dict) or "tables" not in payload:
        raise DatabaseImportError("JSON payload is missing a 'tables' array.")
    tables = payload["tables"]
    if not isinstance(tables, list):
        raise DatabaseImportError("'tables' must be a list.")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for table in tables:
            name = table.get("name")
            columns = table.get("columns", [])
            rows = table.get("rows", [])
            if not name or not isinstance(columns, list):
                raise DatabaseImportError("Each table needs a 'name' and 'columns' list.")
            col_defs = []
            placeholders = []
            col_names = []
            for col in columns:
                col_name = col.get("name") if isinstance(col, dict) else None
                col_type = (col.get("type") if isinstance(col, dict) else None) or "TEXT"
                if not col_name:
                    raise DatabaseImportError("Each column needs a 'name'.")
                safe_type = _sqlite_type(col_type)
                col_defs.append(f'"{col_name.replace(chr(34), chr(34)*2)}" {safe_type}')
                col_names.append(f'"{col_name.replace(chr(34), chr(34)*2)}"')
                placeholders.append("?")
            create_sql = f'CREATE TABLE "{name.replace(chr(34), chr(34)*2)}" ({", ".join(col_defs)})'
            cur.execute(create_sql)
            if rows:
                insert_sql = (
                    f'INSERT INTO "{name.replace(chr(34), chr(34)*2)}" '
                    f'({", ".join(col_names)}) VALUES ({", ".join(placeholders)})'
                )
                for row in rows:
                    if not isinstance(row, list) or len(row) != len(col_names):
                        raise DatabaseImportError(
                            f"Row length mismatch in table {name!r}."
                        )
                    cur.execute(insert_sql, [_coerce(cell) for cell in row])
        conn.commit()
    except (sqlite3.Error, DatabaseImportError) as e:
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)
        if isinstance(e, DatabaseImportError):
            raise
        raise DatabaseImportError(f"Could not build SQLite database from JSON: {e}") from e
    conn.close()


def _sqlite_type(raw_type: str) -> str:
    t = (raw_type or "").upper()
    if any(k in t for k in ("INT",)):
        return "INTEGER"
    if any(k in t for k in ("REAL", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC")):
        return "REAL"
    if "BLOB" in t:
        return "BLOB"
    return "TEXT"


def _coerce(value: Any) -> Any:
    if isinstance(value, bytes):
        return value
    if value is None:
        return None
    return value