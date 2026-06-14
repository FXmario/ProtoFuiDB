from django.urls import path

from core import views

urlpatterns = [
    path("", views.index, name="index"),
    path("register-superuser/", views.register_superuser, name="register-superuser"),
    path("user-detail/", views.user_detail, name="user-detail"),
    path("change-username/", views.change_username, name="change-username"),
]
