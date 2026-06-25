from django.urls import path

from Databases import views

urlpatterns = [
    path("", views.dashboard_index, name="database-dashboard"),
    path("new/", views.database_create, name="database-create"),
    path("new/file-field/", views.database_file_field, name="database-file-field"),
    path("check-connection/", views.check_db_connection_view, name="database-check-connection"),
    path("<uuid:public_id>/", views.database_detail, name="database-detail"),
    path("<uuid:public_id>/sidebar/", views.database_sidebar, name="database-sidebar"),
    path("<uuid:public_id>/sidebar/tables/", views.sidebar_tables, name="sidebar-tables"),
    path("<uuid:public_id>/table/<str:table_name>/", views.table_query, name="table-query"),
    path("<uuid:public_id>/table/<str:table_name>/sort/", views.table_sort_view, name="table-sort"),
    path("<uuid:public_id>/run/", views.run_query_view, name="database-run-query"),
    path("<uuid:public_id>/cell-edit/", views.cell_edit_view, name="database-cell-edit"),
    path("lint-sql/", views.lint_sql_view, name="database-lint-sql"),
]
