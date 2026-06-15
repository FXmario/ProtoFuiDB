from django.urls import path

from Databases import views

urlpatterns = [
    path("", views.dashboard_index, name="database-dashboard"),
    path("new/", views.database_create, name="database-create"),
    path("new/file-field/", views.database_file_field, name="database-file-field"),
    path("check-connection/", views.check_db_connection_view, name="database-check-connection"),
]