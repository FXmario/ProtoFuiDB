from django.urls import path

from Databases import views

urlpatterns = [
    path("", views.dashboard_index, name="database-dashboard"),
]
