import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.files import File
from django.urls import reverse

from Databases.models import Database
from Databases.utils import check_db_connection, DatabaseQueryError, list_tables, run_query

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
