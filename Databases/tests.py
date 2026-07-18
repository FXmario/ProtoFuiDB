import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.files import File
from django.urls import reverse

from Databases.models import Database
from Databases.utils import check_db_connection, DatabaseQueryError, list_tables, run_query, get_primary_key, update_cell, quote_identifier, count_rows
from Databases.io import (
    DatabaseExportError,
    DatabaseImportError,
    export_json,
    export_sql,
    import_sqlite_from_json,
    import_sqlite_from_sql,
)

User = get_user_model()

_mock_psycopg2 = MagicMock()
_mock_MySQLdb = MagicMock()


@pytest.fixture
def mock_db_drivers():
    with patch.dict(sys.modules, {"psycopg2": _mock_psycopg2, "MySQLdb": _mock_MySQLdb}):
        yield


@pytest.mark.django_db
def test_dashboard_index_redirects_to_login_when_not_authenticated(client):
    response = client.get(reverse("database-dashboard"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_dashboard_index_renders_for_authenticated_user(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.get(reverse("database-dashboard"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "No databases yet" in content
    assert "Add Database" in content


@pytest.mark.django_db
def test_dashboard_index_shows_data_when_databases_exist(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)
    db = Database(name="test_db", user="test_user", host="localhost", port=5432, provider=Database.POSTGRESQL, owner=user)
    db.set_password("testpass")
    db.save()

    response = client.get(reverse("database-dashboard"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Database Dashboard" in content
    assert "1" in content


@pytest.mark.django_db
def test_database_create_page_renders(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.get(reverse("database-create"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Add Database" in content


@pytest.mark.django_db
def test_database_create_works(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.post(
        reverse("database-create"),
        {
            "name": "mydb",
            "db_name": "mydb_real",
            "user": "admin",
            "raw_password": "secretpass123",
            "host": "localhost",
            "port": 5432,
            "provider": Database.POSTGRESQL,
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("index")
    assert Database.objects.filter(name="mydb").exists()
    db = Database.objects.get(name="mydb")
    assert db.db_name == "mydb_real"
    assert db.check_password("secretpass123")


@pytest.mark.django_db
def test_database_create_requires_login(client):
    response = client.get(reverse("database-create"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.fixture
def database():
    db = Database(
        name="test_db",
        user="test_user",
        host="localhost",
        port=5432,
        provider=Database.POSTGRESQL,
    )
    db.set_password("my-plain-password")
    db.save()
    return db


    @pytest.mark.django_db
    def test_set_password_encrypts_value(database):
        assert database.password != "my-plain-password"
        assert database.check_password("my-plain-password") is True


@pytest.mark.django_db
def test_check_password_with_correct_password(database):
    assert database.check_password("my-plain-password") is True


@pytest.mark.django_db
def test_check_password_with_wrong_password(database):
    assert database.check_password("wrong-password") is False


@pytest.mark.django_db
def test_provider_choices_are_valid():
    choices = dict(Database.PROVIDER_CHOICES)
    assert Database.POSTGRESQL in choices
    assert Database.MARIADB_MYSQL in choices
    assert Database.SQLITE3 in choices
    assert choices[Database.POSTGRESQL] == "PostgreSQL"
    assert choices[Database.MARIADB_MYSQL] == "MariaDB/MySQL"
    assert choices[Database.SQLITE3] == "SQLite3"


class TestCheckDbConnection:
    @pytest.mark.usefixtures("mock_db_drivers")
    def test_postgresql_success(self):
        mock_conn = MagicMock()
        _mock_psycopg2.connect.reset_mock()
        _mock_psycopg2.connect.return_value = mock_conn

        success, message = check_db_connection(
            provider=Database.POSTGRESQL,
            db_name="testdb",
            user="admin",
            password="pass",
            host="localhost",
            port="5432",
        )

        assert success is True
        assert "Successfully connected to PostgreSQL" in message
        _mock_psycopg2.connect.assert_called_once_with(
            dbname="testdb", user="admin", password="pass", host="localhost", port=5432
        )
        mock_conn.close.assert_called_once()

    @pytest.mark.usefixtures("mock_db_drivers")
    def test_postgresql_failure(self):
        _mock_psycopg2.connect.reset_mock()
        _mock_psycopg2.connect.side_effect = Exception("Connection refused")

        success, message = check_db_connection(
            provider=Database.POSTGRESQL,
            db_name="testdb",
            user="admin",
            password="pass",
            host="localhost",
            port="5432",
        )

        assert success is False
        assert "PostgreSQL connection failed" in message
        _mock_psycopg2.connect.side_effect = None

    @pytest.mark.usefixtures("mock_db_drivers")
    def test_postgresql_default_port(self):
        mock_conn = MagicMock()
        _mock_psycopg2.connect.reset_mock()
        _mock_psycopg2.connect.return_value = mock_conn

        check_db_connection(
            provider=Database.POSTGRESQL,
            db_name="testdb",
            user="admin",
            password="pass",
            host="localhost",
            port="",
        )

        _mock_psycopg2.connect.assert_called_once_with(
            dbname="testdb", user="admin", password="pass", host="localhost", port=5432
        )

    @pytest.mark.usefixtures("mock_db_drivers")
    def test_mariadb_mysql_success(self):
        mock_conn = MagicMock()
        _mock_MySQLdb.connect.reset_mock()
        _mock_MySQLdb.connect.return_value = mock_conn

        success, message = check_db_connection(
            provider=Database.MARIADB_MYSQL,
            db_name="testdb",
            user="admin",
            password="pass",
            host="localhost",
            port="3306",
        )

        assert success is True
        assert "Successfully connected to MariaDB/MySQL" in message
        _mock_MySQLdb.connect.assert_called_once_with(
            db="testdb", user="admin", passwd="pass", host="localhost", port=3306
        )
        mock_conn.close.assert_called_once()

    @pytest.mark.usefixtures("mock_db_drivers")
    def test_mariadb_mysql_failure(self):
        _mock_MySQLdb.connect.reset_mock()
        _mock_MySQLdb.connect.side_effect = Exception("Access denied")

        success, message = check_db_connection(
            provider=Database.MARIADB_MYSQL,
            db_name="testdb",
            user="admin",
            password="pass",
            host="localhost",
            port="3306",
        )

        assert success is False
        assert "MariaDB/MySQL connection failed" in message
        _mock_MySQLdb.connect.side_effect = None

    @pytest.mark.usefixtures("mock_db_drivers")
    def test_mariadb_mysql_default_port(self):
        mock_conn = MagicMock()
        _mock_MySQLdb.connect.reset_mock()
        _mock_MySQLdb.connect.return_value = mock_conn

        check_db_connection(
            provider=Database.MARIADB_MYSQL,
            db_name="testdb",
            user="admin",
            password="pass",
            host="localhost",
            port="",
        )

        _mock_MySQLdb.connect.assert_called_once_with(
            db="testdb", user="admin", passwd="pass", host="localhost", port=3306
        )

    def test_sqlite3_success(self, tmp_path):
        db_file = tmp_path / "test.db"
        db_file.touch()

        success, message = check_db_connection(
            provider=Database.SQLITE3,
            db_name="",
            user="",
            password="",
            host="",
            port="",
            file_path=str(db_file),
        )

        assert success is True
        assert "Successfully connected to SQLite3" in message

    def test_sqlite3_no_file(self):
        success, message = check_db_connection(
            provider=Database.SQLITE3,
            db_name="",
            user="",
            password="",
            host="",
            port="",
            file_path=None,
        )

        assert success is False
        assert "No database file provided" in message

    def test_unsupported_provider(self):
        success, message = check_db_connection(
            provider="unsupported",
            db_name="testdb",
            user="admin",
            password="pass",
            host="localhost",
            port="5432",
        )

        assert success is False
        assert "Unsupported provider" in message


class TestCheckDbConnectionView:
    @pytest.mark.django_db
    @patch("Databases.views.check_db_connection")
    def test_check_connection_success(self, mock_check, client):
        mock_check.return_value = (True, "Successfully connected to PostgreSQL.")
        user = User.objects.create_superuser(username="admin", password="testpass123")
        client.force_login(user)

        response = client.post(
            reverse("database-check-connection"),
            {
                "provider": Database.POSTGRESQL,
                "db_name": "testdb",
                "user": "admin",
                "raw_password": "pass",
                "host": "localhost",
                "port": "5432",
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Successfully connected to PostgreSQL" in content
        assert "alert-success" in content

    @pytest.mark.django_db
    @patch("Databases.views.check_db_connection")
    def test_check_connection_failure(self, mock_check, client):
        mock_check.return_value = (False, "PostgreSQL connection failed: Connection refused")
        user = User.objects.create_superuser(username="admin", password="testpass123")
        client.force_login(user)

        response = client.post(
            reverse("database-check-connection"),
            {
                "provider": Database.POSTGRESQL,
                "db_name": "testdb",
                "user": "admin",
                "raw_password": "pass",
                "host": "localhost",
                "port": "5432",
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "connection failed" in content
        assert "alert-error" in content

    @pytest.mark.django_db
    def test_check_connection_requires_login(self, client):
        response = client.post(reverse("database-check-connection"))
        assert response.status_code == 302
        assert reverse("login") in response.url


@pytest.fixture
def sqlite_database(settings, tmp_path, client):
    user = User.objects.create_superuser(username="sqlite_admin", password="testpass123")
    client.force_login(user)
    settings.MEDIA_ROOT = str(tmp_path)

    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO users (name) VALUES (?)", [("Alice",), ("Bob",)])
    conn.commit()
    conn.close()

    db = Database.objects.create(name="sqlite_test", provider=Database.SQLITE3, owner=user)
    with open(db_file, "rb") as f:
        db.file.save("test.db", File(f))
    db.refresh_from_db()
    return db


@pytest.mark.django_db
def test_database_create_sets_owner(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)
    client.post(
        reverse("database-create"),
        {
            "name": "ownerdb",
            "db_name": "ownerdb_real",
            "user": "admin",
            "raw_password": "secretpass123",
            "host": "localhost",
            "port": 5432,
            "provider": Database.POSTGRESQL,
        },
    )
    db = Database.objects.get(name="ownerdb")
    assert db.owner == user


@pytest.mark.django_db
def test_database_detail_requires_login(client):
    db = Database.objects.create(
        name="test_db", provider=Database.POSTGRESQL, db_name="x", user="x", host="x", port=5432
    )
    response = client.get(reverse("database-detail", kwargs={"public_id": db.public_id}))
    assert response.status_code == 302


@pytest.mark.django_db
def test_database_detail_404_for_other_owner(client, sqlite_database):
    other = User.objects.create_user(username="other", password="testpass123")
    client.force_login(other)
    response = client.get(
        reverse("database-detail", kwargs={"public_id": sqlite_database.public_id})
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_database_detail_renders_sqlite(client, sqlite_database):
    response = client.get(
        reverse("database-detail", kwargs={"public_id": sqlite_database.public_id})
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "users" in content
    assert "SQL Editor" in content


@pytest.mark.django_db
def test_database_detail_sets_status_connected(client, sqlite_database):
    assert sqlite_database.status == Database.UNKNOWN
    client.get(
        reverse("database-detail", kwargs={"public_id": sqlite_database.public_id})
    )
    sqlite_database.refresh_from_db()
    assert sqlite_database.status == Database.CONNECTED


@pytest.mark.django_db
@patch("Databases.views.list_tables", side_effect=DatabaseQueryError("Simulated connection failure"))
def test_database_detail_shows_connection_error(mock_list_tables, client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)
    db = Database.objects.create(
        name="pg_remote",
        provider=Database.POSTGRESQL,
        db_name="x",
        user="x",
        host="x",
        port=5432,
        owner=user,
    )
    db.set_password("x")
    db.save()
    response = client.get(reverse("database-detail", kwargs={"public_id": db.public_id}))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Simulated connection failure" in content


@pytest.mark.django_db
@patch("Databases.views.list_tables", side_effect=DatabaseQueryError("Simulated connection failure"))
def test_database_detail_sets_status_disconnected(mock_list_tables, client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)
    db = Database.objects.create(
        name="pg_remote",
        provider=Database.POSTGRESQL,
        db_name="x",
        user="x",
        host="x",
        port=5432,
        owner=user,
    )
    db.set_password("x")
    db.save()
    assert db.status == Database.UNKNOWN
    client.get(reverse("database-detail", kwargs={"public_id": db.public_id}))
    db.refresh_from_db()
    assert db.status == Database.DISCONNECTED


@pytest.mark.django_db
def test_database_status_defaults_to_unknown(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    db = Database.objects.create(
        name="newdb",
        provider=Database.POSTGRESQL,
        db_name="x",
        user="x",
        host="x",
        port=5432,
        owner=user,
    )
    assert db.status == Database.UNKNOWN


@pytest.mark.django_db
def test_navbar_shows_status_dot_class(client, sqlite_database):
    # Before visiting detail, status is "unknown" on dashboard index
    response = client.get(reverse("database-dashboard"))
    content = response.content.decode()
    assert "status-unknown" in content

    # After visiting detail, status becomes "connected"
    client.get(reverse("database-detail", kwargs={"public_id": sqlite_database.public_id}))
    response = client.get(reverse("database-detail", kwargs={"public_id": sqlite_database.public_id}))
    content = response.content.decode()
    assert "status-connected" in content


@pytest.mark.django_db
def test_navbar_active_tab_has_aria_current(client, sqlite_database):
    response = client.get(reverse("database-detail", kwargs={"public_id": sqlite_database.public_id}))
    content = response.content.decode()
    assert 'aria-current="page"' in content


@pytest.mark.django_db
def test_database_sidebar_renders_tables(client, sqlite_database):
    response = client.get(
        reverse("database-sidebar", kwargs={"public_id": sqlite_database.public_id})
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "users" in content


@pytest.mark.django_db
def test_table_query_default_select(client, sqlite_database):
    response = client.get(
        reverse("table-query", kwargs={"public_id": sqlite_database.public_id, "table_name": "users"})
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "SELECT" in content
    assert "Alice" in content
    assert "Bob" in content


@pytest.mark.django_db
def test_run_query_executes_valid_sql(client, sqlite_database):
    response = client.post(
        reverse("database-run-query", kwargs={"public_id": sqlite_database.public_id}),
        {"query": "SELECT * FROM users WHERE name = 'Alice'"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Alice" in content
    assert "Bob" not in content


@pytest.mark.django_db
def test_run_query_returns_error_for_invalid_sql(client, sqlite_database):
    response = client.post(
        reverse("database-run-query", kwargs={"public_id": sqlite_database.public_id}),
        {"query": "SELECT * FROM nonexistent_table"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Query error" in content


@pytest.mark.django_db
def test_lint_sql_returns_diagnostics_for_invalid_syntax(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)
    response = client.post(
        reverse("database-lint-sql"),
        {"query": "SELEC * FROM users", "provider": Database.SQLITE3},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["diagnostics"]) > 0


@pytest.mark.django_db
def test_lint_sql_returns_empty_for_valid_syntax(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)
    response = client.post(
        reverse("database-lint-sql"),
        {"query": "SELECT * FROM users", "provider": Database.SQLITE3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["diagnostics"] == []


@pytest.mark.django_db
@pytest.mark.usefixtures("mock_db_drivers")
def test_list_tables_postgres():
    _mock_psycopg2.connect.reset_mock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [("users",), ("orders",)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    _mock_psycopg2.connect.return_value = mock_conn

    db = Database.objects.create(
        name="pg",
        provider=Database.POSTGRESQL,
        db_name="db",
        user="u",
        host="h",
        port=5432,
    )
    db.set_password("p")
    db.save()

    tables = list_tables(db)
    assert tables == ["orders", "users"]
    _mock_psycopg2.connect.assert_called_once()
    assert _mock_psycopg2.connect.call_args.kwargs["password"] == "p"


@pytest.mark.django_db
@pytest.mark.usefixtures("mock_db_drivers")
def test_list_tables_mysql():
    _mock_MySQLdb.connect.reset_mock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [("products",), ("users",)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    _mock_MySQLdb.connect.return_value = mock_conn

    db = Database.objects.create(
        name="mysql",
        provider=Database.MARIADB_MYSQL,
        db_name="db",
        user="u",
        host="h",
        port=3306,
    )
    db.set_password("p")
    db.save()

    tables = list_tables(db)
    assert tables == ["products", "users"]
    assert _mock_MySQLdb.connect.call_args.kwargs["passwd"] == "p"


@pytest.mark.django_db
@pytest.mark.usefixtures("mock_db_drivers")
def test_run_query_postgres():
    _mock_psycopg2.connect.reset_mock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "Alice")]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    _mock_psycopg2.connect.return_value = mock_conn

    db = Database.objects.create(
        name="pg",
        provider=Database.POSTGRESQL,
        db_name="db",
        user="u",
        host="h",
        port=5432,
    )
    db.set_password("p")
    db.save()

    columns, rows = run_query(db, "SELECT * FROM users")
    assert columns == ["id", "name"]
    assert rows == [(1, "Alice")]
    mock_cursor.execute.assert_called_once_with("SELECT * FROM users")


# ---------------------------------------------------------------------------
# Cell editing tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_primary_key_sqlite(client, sqlite_database):
    pk = get_primary_key(sqlite_database, "users")
    assert pk == "id"


@pytest.mark.django_db
def test_get_primary_key_returns_none_for_no_pk(settings, tmp_path):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    db_file = tmp_path / "noprimary.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE view_no_pk (a TEXT, b TEXT)")
    conn.close()

    db = Database.objects.create(name="noprimary", provider=Database.SQLITE3, owner=user)
    with open(db_file, "rb") as f:
        db.file.save("noprimary.db", File(f))
    db.refresh_from_db()

    pk = get_primary_key(db, "view_no_pk")
    assert pk is None


@pytest.mark.django_db
def test_update_cell_sqlite(sqlite_database):
    new_val = update_cell(sqlite_database, "users", "name", "1", "Charlie", "id")
    assert new_val == "Charlie"

    conn = sqlite3.connect(sqlite_database.file.path)
    cursor = conn.execute("SELECT name FROM users WHERE id = 1")
    assert cursor.fetchone()[0] == "Charlie"
    conn.close()


@pytest.mark.django_db
def test_update_cell_nonexistent_column(sqlite_database):
    with pytest.raises(DatabaseQueryError):
        update_cell(sqlite_database, "users", "nonexistent_col", "1", "Ghost", "id")


@pytest.mark.django_db
def test_cell_edit_view_updates_value(client, sqlite_database):
    response = client.post(
        reverse("database-cell-edit", kwargs={"public_id": sqlite_database.public_id}),
        {
            "table": "users",
            "column": "name",
            "row_id": "1",
            "value": "UpdatedName",
        },
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "UpdatedName" in content
    conn = sqlite3.connect(sqlite_database.file.path)
    cursor = conn.execute("SELECT name FROM users WHERE id = 1")
    assert cursor.fetchone()[0] == "UpdatedName"
    conn.close()


@pytest.mark.django_db
def test_cell_edit_view_no_pk(settings, tmp_path, client):
    user = User.objects.create_superuser(username="admin2", password="testpass123")
    client.force_login(user)
    db_file = tmp_path / "noprimary2.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE no_pk_table (a TEXT, b TEXT)")
    conn.close()

    db = Database.objects.create(name="npk", provider=Database.SQLITE3, owner=user)
    with open(db_file, "rb") as f:
        db.file.save("noprimary2.db", File(f))
    db.refresh_from_db()

    response = client.post(
        reverse("database-cell-edit", kwargs={"public_id": db.public_id}),
        {
            "table": "no_pk_table",
            "column": "a",
            "row_id": "1",
            "value": "test",
        },
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_cell_edit_view_missing_params(client, sqlite_database):
    response = client.post(
        reverse("database-cell-edit", kwargs={"public_id": sqlite_database.public_id}),
        {"table": "users"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_cell_edit_view_requires_login(settings, tmp_path, client):
    user = User.objects.create_superuser(username="login_test", password="testpass123")
    settings.MEDIA_ROOT = str(tmp_path)
    db_file = tmp_path / "login_test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE tbl (id INTEGER PRIMARY KEY, v TEXT)")
    conn.close()

    from django.test import Client
    unauth_client = Client()
    db = Database.objects.create(name="lt_db", provider=Database.SQLITE3, owner=user)
    with open(db_file, "rb") as f:
        db.file.save("login_test.db", File(f))
    db.refresh_from_db()

    response = unauth_client.post(
        reverse("database-cell-edit", kwargs={"public_id": db.public_id}),
        {
            "table": "tbl",
            "column": "v",
            "row_id": "1",
            "value": "test",
        },
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_cell_edit_view_404_for_other_owner(client, sqlite_database):
    other = User.objects.create_user(username="other_user", password="testpass123")
    client.force_login(other)
    response = client.post(
        reverse("database-cell-edit", kwargs={"public_id": sqlite_database.public_id}),
        {
            "table": "users",
            "column": "name",
            "row_id": "1",
            "value": "test",
        },
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_database_detail_includes_editable_badge(client, sqlite_database):
    response = client.get(
        reverse("database-detail", kwargs={"public_id": sqlite_database.public_id})
    )
    content = response.content.decode()
    assert "Editable" in content


@pytest.mark.django_db
def test_database_detail_includes_readonly_badge(settings, tmp_path, client):
    user = User.objects.create_superuser(username="ro_admin", password="testpass123")
    client.force_login(user)
    settings.MEDIA_ROOT = str(tmp_path)

    db_file = tmp_path / "readonly.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE no_pk_tbl (val TEXT)")
    conn.close()

    db = Database.objects.create(name="ro_db", provider=Database.SQLITE3, owner=user)
    with open(db_file, "rb") as f:
        db.file.save("readonly.db", File(f))
    db.refresh_from_db()

    response = client.get(reverse("database-detail", kwargs={"public_id": db.public_id}))
    content = response.content.decode()
    assert "Read-only" in content


# ---------------------------------------------------------------------------
# Sorting tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_table_sort_view_asc(client, sqlite_database):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "users"},
        ),
        {"sort": "name", "dir": "asc"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Alice" in content
    assert "Bob" in content
    assert content.index("Alice") < content.index("Bob")


@pytest.mark.django_db
def test_table_sort_view_desc(client, sqlite_database):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "users"},
        ),
        {"sort": "name", "dir": "desc"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert content.index("Bob") < content.index("Alice")


@pytest.mark.django_db
def test_table_sort_view_invalid_dir_defaults_asc(client, sqlite_database):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "users"},
        ),
        {"sort": "name", "dir": "sideways"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert content.index("Alice") < content.index("Bob")


@pytest.mark.django_db
def test_table_sort_view_invalid_column_ignored(client, sqlite_database):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "users"},
        ),
        {"sort": "nonexistent_col", "dir": "asc"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Alice" in content
    assert "Bob" in content


@pytest.mark.django_db
def test_table_sort_view_nonexistent_table(client, sqlite_database):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "ghost"},
        ),
        {"sort": "name", "dir": "asc"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_table_sort_view_requires_login(client, sqlite_database):
    from django.test import Client
    unauth_client = Client()
    response = unauth_client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "users"},
        ),
        {"sort": "name", "dir": "asc"},
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_table_sort_view_asc_shows_up_arrow(client, sqlite_database):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "users"},
        ),
        {"sort": "name", "dir": "asc"},
    )
    content = response.content.decode()
    assert "rotate-180" in content


@pytest.mark.django_db
def test_table_sort_view_desc_shows_down_arrow(client, sqlite_database):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database.public_id, "table_name": "users"},
        ),
        {"sort": "name", "dir": "desc"},
    )
    content = response.content.decode()
    assert "rotate-180" not in content


@pytest.mark.django_db
def test_database_detail_includes_sort_headers(client, sqlite_database):
    response = client.get(
        reverse("database-detail", kwargs={"public_id": sqlite_database.public_id})
    )
    content = response.content.decode()
    assert "/sort" in content
    assert "sort=" in content


# ---------------------------------------------------------------------------
# Sidebar pagination + search tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_database_many_tables(settings, tmp_path, client):
    user = User.objects.create_superuser(username="tables_admin", password="testpass123")
    client.force_login(user)
    settings.MEDIA_ROOT = str(tmp_path)

    db_file = tmp_path / "many_tables.db"
    conn = sqlite3.connect(str(db_file))
    for i in range(15):
        conn.execute(f"CREATE TABLE table_{i:02d} (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    db = Database.objects.create(name="many_tables", provider=Database.SQLITE3, owner=user)
    with open(db_file, "rb") as f:
        db.file.save("many_tables.db", File(f))
    db.refresh_from_db()
    return db


@pytest.mark.django_db
def test_sidebar_tables_pagination(client, sqlite_database_many_tables):
    response = client.get(
        reverse("sidebar-tables", kwargs={"public_id": sqlite_database_many_tables.public_id})
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "table_00" in content
    assert "table_09" in content
    assert "table_10" not in content
    assert "Page 1 of 2" in content

    response = client.get(
        reverse("sidebar-tables", kwargs={"public_id": sqlite_database_many_tables.public_id}),
        {"page": 2},
    )
    content = response.content.decode()
    assert "table_10" in content
    assert "table_14" in content
    assert "table_00" not in content
    assert "Page 2 of 2" in content


@pytest.mark.django_db
def test_sidebar_tables_search(client, sqlite_database_many_tables):
    response = client.get(
        reverse("sidebar-tables", kwargs={"public_id": sqlite_database_many_tables.public_id}),
        {"q": "table_01"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "table_01" in content
    assert "table_00" not in content
    assert "table_02" not in content


@pytest.mark.django_db
def test_sidebar_tables_requires_login(client, sqlite_database_many_tables):
    from django.test import Client
    unauth_client = Client()
    response = unauth_client.get(
        reverse("sidebar-tables", kwargs={"public_id": sqlite_database_many_tables.public_id})
    )
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# Records pagination + resize/page-size tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_database_many_rows(settings, tmp_path, client):
    user = User.objects.create_superuser(username="rows_admin", password="testpass123")
    client.force_login(user)
    settings.MEDIA_ROOT = str(tmp_path)

    db_file = tmp_path / "many_rows.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE big_table (id INTEGER PRIMARY KEY, value TEXT)")
    conn.executemany(
        "INSERT INTO big_table (value) VALUES (?)",
        [(f"value_{i}",) for i in range(60)],
    )
    conn.commit()
    conn.close()

    db = Database.objects.create(name="many_rows", provider=Database.SQLITE3, owner=user)
    with open(db_file, "rb") as f:
        db.file.save("many_rows.db", File(f))
    db.refresh_from_db()
    return db


@pytest.mark.django_db
def test_database_detail_paginates_records(client, sqlite_database_many_rows):
    response = client.get(
        reverse("database-detail", kwargs={"public_id": sqlite_database_many_rows.public_id})
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "value_0" in content
    assert "value_24" in content
    assert "value_25" not in content
    assert "LIMIT 25" in content
    assert "Page 1 of 3" in content
    assert "resize-y" in content


@pytest.mark.django_db
def test_table_sort_view_pagination(client, sqlite_database_many_rows):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database_many_rows.public_id, "table_name": "big_table"},
        ),
        {"page": 2},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "value_25" in content
    assert "value_49" in content
    assert "value_50" not in content
    assert "value_0" not in content
    assert "Page 2 of 3" in content


@pytest.mark.django_db
def test_table_sort_view_per_page(client, sqlite_database_many_rows):
    response = client.get(
        reverse(
            "table-sort",
            kwargs={"public_id": sqlite_database_many_rows.public_id, "table_name": "big_table"},
        ),
        {"per_page": 50},
    )
    content = response.content.decode()
    assert "value_0" in content
    assert "value_49" in content
    assert "value_50" not in content
    assert "Page 1 of 2" in content


@pytest.mark.django_db
def test_count_rows(sqlite_database_many_rows):
    assert count_rows(sqlite_database_many_rows, "big_table") == 60


# ---------------------------------------------------------------------------
# Provider-aware identifier quoting tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quote_identifier_sqlite_uses_double_quotes():
    db = Database(provider=Database.SQLITE3)
    assert quote_identifier(db, "my_table") == '"my_table"'
    assert quote_identifier(db, 'has"quote') == '"has""quote"'


@pytest.mark.django_db
def test_quote_identifier_postgres_uses_double_quotes():
    db = Database(provider=Database.POSTGRESQL)
    assert quote_identifier(db, "my_table") == '"my_table"'
    assert quote_identifier(db, 'has"quote') == '"has""quote"'


@pytest.mark.django_db
def test_quote_identifier_mysql_uses_backticks():
    db = Database(provider=Database.MARIADB_MYSQL)
    assert quote_identifier(db, "my_table") == '`my_table`'
    assert quote_identifier(db, "has`tick") == '`has``tick`'


# ---------------------------------------------------------------------------
# MariaDB database_detail uses backtick-quoted queries
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("mock_db_drivers")
def test_database_detail_mysql_uses_backtick_quoting(client):
    _mock_MySQLdb.connect.reset_mock()

    call_count = [0]
    mock_cursor = MagicMock()

    def fake_execute(query, *args, **kwargs):
        call_count[0] += 1
        if "SHOW TABLES" in query:
            mock_cursor.fetchall.return_value = [("users",)]
            mock_cursor.description = None
        elif "SHOW COLUMNS" in query:
            mock_cursor.fetchall.return_value = [
                ("id", "int(11)", "NO", "PRI", None, ""),
                ("name", "varchar(255)", "YES", "", None, ""),
            ]
        elif "SELECT * FROM" in query and ("LIMIT 25" in query or "LIMIT 50" in query or "LIMIT 100" in query):
            mock_cursor.description = [("id",), ("name",)]
            mock_cursor.fetchall.return_value = [(1, "Alice")]
        elif "SELECT COUNT(*)" in query:
            mock_cursor.fetchone.return_value = (1,)
        else:
            mock_cursor.fetchall.return_value = []
            mock_cursor.description = None

    mock_cursor.execute.side_effect = fake_execute
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    _mock_MySQLdb.connect.return_value = mock_conn

    user = User.objects.create_superuser(username="mysql_admin", password="testpass123")
    client.force_login(user)
    db = Database.objects.create(
        name="mysql_db",
        provider=Database.MARIADB_MYSQL,
        db_name="testdb",
        user="u",
        host="h",
        port=3306,
        owner=user,
    )
    db.set_password("p")
    db.save()

    response = client.get(reverse("database-detail", kwargs={"public_id": db.public_id}))
    assert response.status_code == 200

    content = response.content.decode()
    assert "`users`" in content
    assert "SELECT * FROM `users`" in content
    assert "LIMIT 25" in content
    assert "SELECT * FROM \"users\"" not in content


# ---------------------------------------------------------------------------
# Export / Import tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_export_json_returns_all_tables(sqlite_database):
    payload = export_json(sqlite_database)
    assert payload["database"] == "sqlite_test"
    table_names = [t["name"] for t in payload["tables"]]
    assert "users" in table_names
    users_table = next(t for t in payload["tables"] if t["name"] == "users")
    col_names = [c["name"] for c in users_table["columns"]]
    assert col_names == ["id", "name"]
    row_values = [r[1] for r in users_table["rows"]]
    assert set(row_values) == {"Alice", "Bob"}


@pytest.mark.django_db
def test_export_json_view_returns_json_attachment(client, sqlite_database):
    response = client.get(
        reverse("database-export", kwargs={"public_id": sqlite_database.public_id}),
        {"format": "json"},
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert 'attachment; filename="sqlite_test.json"' in response["Content-Disposition"]
    body = response.json()
    assert body["database"] == "sqlite_test"
    assert any(t["name"] == "users" for t in body["tables"])


@pytest.mark.django_db
def test_export_sql_view_for_sqlite(client, sqlite_database):
    response = client.get(
        reverse("database-export", kwargs={"public_id": sqlite_database.public_id}),
        {"format": "sql"},
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/sql"
    assert 'attachment; filename="sqlite_test.sql"' in response["Content-Disposition"]
    body = response.content.decode()
    assert "CREATE TABLE" in body
    assert "users" in body


@pytest.mark.django_db
def test_database_export_requires_login(client):
    db = Database.objects.create(name="x", provider=Database.SQLITE3)
    response = client.get(reverse("database-export", kwargs={"public_id": db.public_id}))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_database_export_404_for_other_owner(client, sqlite_database):
    other = User.objects.create_user(username="intruder", password="testpass123")
    client.force_login(other)
    response = client.get(
        reverse("database-export", kwargs={"public_id": sqlite_database.public_id}),
        {"format": "json"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_database_export_unsupported_format(client, sqlite_database):
    response = client.get(
        reverse("database-export", kwargs={"public_id": sqlite_database.public_id}),
        {"format": "csv"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_database_detail_renders_export_dropdown(client, sqlite_database):
    response = client.get(
        reverse("database-detail", kwargs={"public_id": sqlite_database.public_id})
    )
    content = response.content.decode()
    assert "Export" in content
    assert "?format=sql" in content
    assert "?format=json" in content


def test_import_sqlite_from_sql_creates_table(tmp_path):
    db_path = tmp_path / "imported.db"
    sql = """
    CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT);
    INSERT INTO items (label) VALUES ('alpha'), ('beta');
    """
    import_sqlite_from_sql(str(db_path), sql)
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT label FROM items ORDER BY id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["alpha", "beta"]


def test_import_sqlite_from_sql_invalid_sql_raises(tmp_path):
    db_path = tmp_path / "bad.db"
    with pytest.raises(DatabaseImportError):
        import_sqlite_from_sql(str(db_path), "THIS IS NOT SQL;")
    assert not db_path.exists()


def test_import_sqlite_from_json_roundtrip(tmp_path):
    db_path = tmp_path / "rt.db"
    payload = {
        "database": "rt",
        "provider": Database.SQLITE3,
        "tables": [
            {
                "name": "people",
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "name", "type": "TEXT"},
                ],
                "rows": [[1, "Alice"], [2, "Bob"]],
            }
        ],
    }
    import_sqlite_from_json(str(db_path), payload)
    conn = sqlite3.connect(str(db_path))
    cols = conn.execute("PRAGMA table_info(people)").fetchall()
    rows = conn.execute("SELECT id, name FROM people ORDER BY id").fetchall()
    conn.close()
    assert [c[1] for c in cols] == ["id", "name"]
    assert rows == [(1, "Alice"), (2, "Bob")]


def test_import_sqlite_from_json_missing_tables_raises(tmp_path):
    db_path = tmp_path / "bad.db"
    with pytest.raises(DatabaseImportError):
        import_sqlite_from_json(str(db_path), {"database": "x"})
    assert not db_path.exists()


@pytest.mark.django_db
def test_database_import_creates_sqlite_records(settings, tmp_path, client):
    user = User.objects.create_superuser(username="imp_admin", password="testpass123")
    client.force_login(user)
    settings.MEDIA_ROOT = str(tmp_path)

    sql = (
        "CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT);"
        "INSERT INTO notes (body) VALUES ('hello'), ('world');"
    )

    import io as _io

    upload = _io.BytesIO(sql.encode("utf-8"))
    upload.name = "imp.sql"
    response = client.post(
        reverse("database-import"),
        {"name": "ImportedNotes", "file": upload},
    )
    assert response.status_code == 302

    new_db = Database.objects.get(name="ImportedNotes")
    assert new_db.provider == Database.SQLITE3
    assert new_db.owner == user
    assert new_db.file.name  # FileField populated
    conn = sqlite3.connect(new_db.file.path)
    rows = conn.execute("SELECT body FROM notes ORDER BY id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["hello", "world"]


@pytest.mark.django_db
def test_database_import_json_creates_sqlite_record(settings, tmp_path, client):
    user = User.objects.create_superuser(username="json_admin", password="testpass123")
    client.force_login(user)
    settings.MEDIA_ROOT = str(tmp_path)

    import io as _io
    import json as _json

    payload = {
        "database": "from_json",
        "tables": [
            {
                "name": "widgets",
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "qty", "type": "INTEGER"},
                ],
                "rows": [[1, 10], [2, 20]],
            }
        ],
    }
    upload = _io.BytesIO(_json.dumps(payload).encode("utf-8"))
    upload.name = "widgets.json"
    response = client.post(
        reverse("database-import"),
        {"name": "WidgetsImport", "file": upload},
    )
    assert response.status_code == 302
    new_db = Database.objects.get(name="WidgetsImport")
    assert new_db.provider == Database.SQLITE3
    conn = sqlite3.connect(new_db.file.path)
    rows = conn.execute("SELECT id, qty FROM widgets ORDER BY id").fetchall()
    conn.close()
    assert rows == [(1, 10), (2, 20)]


@pytest.mark.django_db
def test_database_import_rejects_unsupported_format(client):
    user = User.objects.create_superuser(username="fmt_admin", password="testpass123")
    client.force_login(user)
    import io as _io

    upload = _io.BytesIO(b"hi")
    upload.name = "evil.csv"
    response = client.post(reverse("database-import"), {"file": upload})
    assert response.status_code == 400
    assert "Only .sql and .json" in response.content.decode()


@pytest.mark.django_db
def test_database_import_requires_login(client):
    import io as _io

    upload = _io.BytesIO(b"CREATE TABLE x (id INTEGER);")
    upload.name = "x.sql"
    response = client.post(reverse("database-import"), {"file": upload})
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_database_import_missing_file_returns_400(client):
    user = User.objects.create_superuser(username="nf_admin", password="testpass123")
    client.force_login(user)
    response = client.post(reverse("database-import"), {})
    assert response.status_code == 400
    assert "No file was uploaded" in response.content.decode()


@pytest.mark.django_db
def test_database_create_page_renders_import_form(client):
    user = User.objects.create_superuser(username="imp_page", password="testpass123")
    client.force_login(user)
    response = client.get(reverse("database-create"))
    content = response.content.decode()
    assert "Import from file" in content
    assert reverse("database-import") in content


# ---------------------------------------------------------------------------
# Navbar tabs-lift restyle tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_navbar_uses_tabs_lift_class(client, sqlite_database):
    response = client.get(reverse("database-detail", kwargs={"public_id": sqlite_database.public_id}))
    content = response.content.decode()
    assert 'role="tablist"' in content
    assert "tabs tabs-lift" in content
    assert 'role="tab"' in content


@pytest.mark.django_db
def test_navbar_active_tab_has_tab_active_class(client, sqlite_database):
    response = client.get(reverse("database-detail", kwargs={"public_id": sqlite_database.public_id}))
    content = response.content.decode()
    assert "tab-active" in content
