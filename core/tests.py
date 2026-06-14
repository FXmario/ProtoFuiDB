import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.django_db
def test_login_page_renders_when_users_exist(client):
    User.objects.create_superuser(username="admin", password="testpass123")

    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Login to FuiDB" in content
    assert "id_username" in content
    assert "id_password" in content


@pytest.mark.django_db
def test_login_page_redirects_to_index_when_no_users_exist(client):
    response = client.get(reverse("login"))
    assert response.status_code == 302
    assert response.url == reverse("index")


@pytest.mark.django_db
def test_user_detail_requires_login(client):
    response = client.get(reverse("user-detail"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_user_detail_renders_for_authenticated_user(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.get(reverse("user-detail"))
    assert response.status_code == 200
    content = response.content.decode()
    assert user.username in content
    assert "Change Password" in content
    assert "Change Username" in content


@pytest.mark.django_db
def test_change_username_page_renders(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.get(reverse("change-username"))
    assert response.status_code == 200
    assert "Change Username" in response.content.decode()


@pytest.mark.django_db
def test_change_username_works(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.post(
        reverse("change-username"),
        {"new_username": "newadmin"},
    )
    assert response.status_code == 302
    assert response.url == reverse("user-detail")
    user.refresh_from_db()
    assert user.username == "newadmin"


@pytest.mark.django_db
def test_change_username_duplicate_rejected(client):
    User.objects.create_superuser(username="otheruser", password="testpass123")
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.post(
        reverse("change-username"),
        {"new_username": "otheruser"},
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.username == "admin"


@pytest.mark.django_db
def test_logout_logs_user_out(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert response.url == reverse("index")
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_password_change_page_renders(client):
    user = User.objects.create_superuser(username="admin", password="oldpass123")
    client.force_login(user)

    response = client.get(reverse("password_change"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Change Password" in content
    assert "id_old_password" in content
    assert "id_new_password1" in content
    assert "id_new_password2" in content


@pytest.mark.django_db
def test_password_change_works(client):
    user = User.objects.create_superuser(username="admin", password="oldpass123")
    client.force_login(user)

    response = client.post(
        reverse("password_change"),
        {
            "old_password": "oldpass123",
            "new_password1": "newstrongpass123",
            "new_password2": "newstrongpass123",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("password_change_done")

    user.refresh_from_db()
    assert user.check_password("newstrongpass123")


@pytest.mark.django_db
def test_password_change_done_page_renders(client):
    user = User.objects.create_superuser(username="admin", password="testpass123")
    client.force_login(user)

    response = client.get(reverse("password_change_done"))
    assert response.status_code == 200
    assert "Password Changed" in response.content.decode()


@pytest.mark.django_db
def test_index_redirects_to_register_when_no_users_exist(client):
    response = client.get(reverse("index"))
    assert response.status_code == 302
    assert response.url == reverse("register-superuser")


@pytest.mark.django_db
def test_index_redirects_to_database_dashboard_when_users_exist(client):
    User.objects.create_superuser(username="admin", password="testpass123")

    response = client.get(reverse("index"))
    assert response.status_code == 302
    assert response.url == reverse("database-dashboard")


@pytest.mark.django_db
def test_register_superuser_page_shows_when_no_users_exist(client):
    response = client.get(reverse("register-superuser"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Create Superuser" in content
    assert "username" in content
    assert "password1" in content
    assert "password2" in content


@pytest.mark.django_db
def test_register_superuser_blocked_when_users_exist(client):
    User.objects.create_superuser(username="admin", password="testpass123")

    response = client.get(reverse("register-superuser"))
    assert response.status_code == 302
    assert response.url == reverse("index")


@pytest.mark.django_db
def test_register_superuser_creates_superuser(client):
    response = client.post(
        reverse("register-superuser"),
        {
            "username": "admin",
            "password1": "complex-password-123",
            "password2": "complex-password-123",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("database-dashboard")
    assert User.objects.filter(username="admin").exists()

    user = User.objects.get(username="admin")
    assert user.is_superuser is True
    assert user.is_staff is True


@pytest.mark.django_db
def test_register_superuser_invalid_form_does_not_create_user(client):
    response = client.post(
        reverse("register-superuser"),
        {
            "username": "admin",
            "password1": "complex-password-123",
            "password2": "different-password",
        },
    )

    assert response.status_code == 200
    assert not User.objects.filter(username="admin").exists()
    content = response.content.decode()
    assert "errorlist" in content or "didn" in content
