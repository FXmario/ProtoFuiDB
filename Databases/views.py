import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from Databases.models import Database
from Databases.forms import DatabaseForm
from Databases.utils import (
    check_db_connection,
    DatabaseQueryError,
    get_columns,
    get_primary_key,
    lint_sql,
    list_tables,
    run_query,
    update_cell,
    UnsupportedProviderError,
)

SQLITE3 = Database.SQLITE3


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _get_database_or_404(request: HttpRequest, public_id: str) -> Database:
    return get_object_or_404(Database, public_id=public_id, owner=request.user)


def _build_schema(database: Database) -> dict[str, list[str]]:
    try:
        return {
            table: [col[0] for col in get_columns(database, table)]
            for table in list_tables(database)
        }
    except Exception:
        return {}


@login_required
def dashboard_index(request: HttpRequest) -> HttpResponse:
    databases = Database.objects.filter(owner=request.user)
    context = {"databases": databases}
    return render(request, "Databases/dashboard_index.html", context)


@login_required
def database_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = DatabaseForm(request.POST, request.FILES)
        if form.is_valid():
            db = form.save(commit=False)
            db.owner = request.user
            raw_password = form.cleaned_data.get("raw_password")
            if raw_password:
                db.set_password(raw_password)
            db.save()
            return redirect(reverse("index"))
    else:
        form = DatabaseForm()

    return render(request, "Databases/database_create.html", {"form": form})


@login_required
def database_file_field(request: HttpRequest) -> HttpResponse:
    provider = request.GET.get("provider", "")
    show_file_field = provider == SQLITE3
    return render(request, "Databases/partials/file_field.html", {
        "show_file_field": show_file_field,
    })


@login_required
def check_db_connection_view(request: HttpRequest) -> HttpResponse:
    provider = request.POST.get("provider", "")
    db_name = request.POST.get("db_name", "")
    user = request.POST.get("user", "")
    raw_password = request.POST.get("raw_password", "")
    host = request.POST.get("host", "")
    port = request.POST.get("port", "")

    file_path = None
    if provider == SQLITE3:
        uploaded_file = request.FILES.get("file")
        if uploaded_file:
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                file_path = tmp.name

    success, message = check_db_connection(
        provider=provider,
        db_name=db_name,
        user=user,
        password=raw_password,
        host=host,
        port=port,
        file_path=file_path,
    )

    if file_path:
        import os
        os.unlink(file_path)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return render(request, "Databases/partials/toast_messages.html", {"messages": messages.get_messages(request)})


@login_required
def database_detail(request: HttpRequest, public_id: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)
    context = {
        "database": database,
        "provider_label": dict(Database.PROVIDER_CHOICES).get(database.provider, database.provider),
    }

    try:
        context["tables"] = list_tables(database)
        context["schema_json"] = json.dumps(_build_schema(database))
        context["error"] = None
        if database.status != Database.CONNECTED:
            database.status = Database.CONNECTED
            database.save(update_fields=["status"])
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        context["tables"] = []
        context["schema_json"] = "{}"
        context["error"] = str(e)
        if database.status != Database.DISCONNECTED:
            database.status = Database.DISCONNECTED
            database.save(update_fields=["status"])
        return render(request, "Databases/database_detail.html", context)

    active_table = request.GET.get("table", "") or (context["tables"][0] if context["tables"] else "")
    if active_table:
        if active_table in context["tables"]:
            try:
                query = f"SELECT * FROM {_quote_identifier(active_table)} LIMIT 100"
                columns, rows = run_query(database, query)
                context["query"] = query
                context["columns"] = columns
                context["rows"] = rows
                context["active_table"] = active_table
                pk_col = get_primary_key(database, active_table)
                context["pk_column"] = pk_col
                context["pk_index"] = columns.index(pk_col) if pk_col and pk_col in columns else None
                context["sort_column"] = ""
                context["sort_dir"] = "asc"
            except (DatabaseQueryError, UnsupportedProviderError) as e:
                context["query"] = f"SELECT * FROM {_quote_identifier(active_table)} LIMIT 100"
                context["columns"] = []
                context["rows"] = []
                context["error"] = str(e)
                context["active_table"] = active_table
                context["pk_column"] = None
                context["pk_index"] = None
                context["sort_column"] = ""
                context["sort_dir"] = "asc"
        else:
            context["error"] = f"Table {active_table!r} does not exist."

    return render(request, "Databases/database_detail.html", context)


@login_required
def database_sidebar(request: HttpRequest, public_id: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)
    context = {
        "database": database,
        "provider_label": dict(Database.PROVIDER_CHOICES).get(database.provider, database.provider),
    }

    try:
        context["tables"] = list_tables(database)
        context["error"] = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        context["tables"] = []
        context["error"] = str(e)

    return render(request, "sidebar.html", context)


@login_required
def table_query(request: HttpRequest, public_id: str, table_name: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)

    try:
        tables = list_tables(database)
        if table_name not in tables:
            return HttpResponse(f"Table {table_name!r} does not exist.", status=404)

        query = f"SELECT * FROM {_quote_identifier(table_name)} LIMIT 100"
        columns, rows = run_query(database, query)
        error = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        query = f"SELECT * FROM {_quote_identifier(table_name)} LIMIT 100"
        columns, rows = [], []
        error = str(e)

    context = {
        "database": database,
        "query": query,
        "columns": columns,
        "rows": rows,
        "error": error,
        "schema_json": json.dumps(_build_schema(database)),
        "active_table": table_name,
        "pk_column": get_primary_key(database, table_name),
        "pk_index": None,
    }
    try:
        pk_col = context["pk_column"]
        if pk_col and pk_col in columns:
            context["pk_index"] = columns.index(pk_col)
    except Exception:
        pass
    return render(request, "Databases/partials/query_panel.html", context)


@login_required
def run_query_view(request: HttpRequest, public_id: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)
    query = request.POST.get("query", "").strip()
    active_table = request.POST.get("active_table", "").strip()
    pk_column = request.POST.get("pk_column", "").strip() or None

    try:
        columns, rows = run_query(database, query)
        error = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        columns, rows = [], []
        error = str(e)

    context = {
        "database": database,
        "query": query,
        "columns": columns,
        "rows": rows,
        "error": error,
        "active_table": active_table,
        "pk_column": pk_column,
        "pk_index": None,
    }
    if pk_column and pk_column in columns:
        context["pk_index"] = columns.index(pk_column)
    return render(request, "Databases/partials/query_results.html", context)


@login_required
def table_sort_view(request: HttpRequest, public_id: str, table_name: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)
    sort_column = request.GET.get("sort", "").strip()
    sort_dir = request.GET.get("dir", "asc").strip().lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    try:
        tables = list_tables(database)
        if table_name not in tables:
            return HttpResponse(f"Table {table_name!r} does not exist.", status=404)

        column_names = [c[0] for c in get_columns(database, table_name)]
        if sort_column and sort_column not in column_names:
            sort_column = ""

        order_clause = ""
        if sort_column:
            order_clause = f" ORDER BY {_quote_identifier(sort_column)} {sort_dir.upper()}"

        query = f"SELECT * FROM {_quote_identifier(table_name)}{order_clause} LIMIT 100"
        columns, rows = run_query(database, query)
        error = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        query = f"SELECT * FROM {_quote_identifier(table_name)} LIMIT 100"
        columns, rows = [], []
        error = str(e)

    pk_col = get_primary_key(database, table_name)
    pk_index = None
    if pk_col and pk_col in columns:
        pk_index = columns.index(pk_col)

    context = {
        "database": database,
        "columns": columns,
        "rows": rows,
        "error": error,
        "active_table": table_name,
        "pk_column": pk_col,
        "pk_index": pk_index,
        "sort_column": sort_column,
        "sort_dir": sort_dir,
    }
    return render(request, "Databases/partials/query_results.html", context)


@login_required
def cell_edit_view(request: HttpRequest, public_id: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    table = request.POST.get("table", "").strip()
    column = request.POST.get("column", "").strip()
    row_id = request.POST.get("row_id", "").strip()
    value = request.POST.get("value", "").strip()

    if not all([table, column, row_id]):
        return JsonResponse({"error": "Missing parameters"}, status=400)

    pk_column = get_primary_key(database, table)
    if not pk_column:
        return JsonResponse(
            {"error": "This table has no primary key — editing is disabled."},
            status=403,
        )

    try:
        new_value = update_cell(database, table, column, row_id, value, pk_column)
        error = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        new_value = value
        error = str(e)

    context = {
        "value": new_value,
        "error": error,
        "column": column,
    }
    return render(request, "Databases/partials/cell_edit.html", context)


@login_required
def lint_sql_view(request: HttpRequest) -> HttpResponse:
    query = request.POST.get("query", "")
    provider = request.POST.get("provider", Database.SQLITE3)
    diagnostics = lint_sql(query, provider)
    return JsonResponse({"diagnostics": diagnostics})
