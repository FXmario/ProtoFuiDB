import sys
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.urls import reverse

from Databases.models import Database
from Databases.utils import check_db_connection

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
    db = Database(name="test_db", user="test_user", host="localhost", port=5432, provider=Database.POSTGRESQL)
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
def test_set_password_hashes_value(database):
    assert database.password != "my-plain-password"
    assert database.password.startswith("pbkdf2_sha256$")


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
