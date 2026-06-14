import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from Databases.models import Database

User = get_user_model()


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
            "user": "admin",
            "raw_password": "secretpass123",
            "host": "localhost",
            "port": 5432,
            "provider": Database.POSTGRESQL,
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("database-dashboard")
    assert Database.objects.filter(name="mydb").exists()
    db = Database.objects.get(name="mydb")
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
