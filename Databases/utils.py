import sqlite3

from .models import Database


def check_db_connection(provider, db_name, user, password, host, port, file_path=None):
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
        # error_type = type(e).__name__
        if provider == Database.POSTGRESQL:
            return False, f"PostgreSQL connection failed: {e}"
        elif provider == Database.MARIADB_MYSQL:
            return False, f"MariaDB/MySQL connection failed: {e}"
        elif provider == Database.SQLITE3:
            return False, f"SQLite3 connection failed: {e}"
        return False, f"Connection failed: {e}"

    provider_label = dict(Database.PROVIDER_CHOICES).get(provider, provider)
    return True, f"Successfully connected to {provider_label}."
