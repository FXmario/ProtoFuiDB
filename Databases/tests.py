import pytest

from Databases.models import Database


@pytest.fixture
def database():
    db = Database(name="test_db", user="test_user", host="localhost")
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
