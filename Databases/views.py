import json
from typing import Any

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
    open_connection,
    quote_identifier,
    run_query,
    run_query_with_params,
    update_cell,
    UnsupportedProviderError,
)

SQLITE3 = Database.SQLITE3


def _get_database_or_404(request: HttpRequest, public_id: str) -> Database:
    return get_object_or_404(Database, public_id=public_id, owner=request.user)


TABLES_PER_PAGE = 10
DEFAULT_RECORDS_PER_PAGE = 25


def _build_schema(database: Database) -> dict[str, list[str]]:
    try:
        return {
            table: [col[0] for col in get_columns(database, table)]
            for table in list_tables(database)
        }
    except Exception:
        return {}


def _paginate_tables(all_tables: list[str], page: int, q: str) -> tuple[list[str], int, int]:
    """Return (paginated_tables, page, total_pages) for the sidebar list."""
    filtered = [t for t in all_tables if q.lower() in t.lower()] if q else all_tables
    total_pages = max(1, (len(filtered) + TABLES_PER_PAGE - 1) // TABLES_PER_PAGE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * TABLES_PER_PAGE
    return filtered[start : start + TABLES_PER_PAGE], page, total_pages


def _parse_records_pagination(request: HttpRequest) -> tuple[int, int]:
    """Return (page, per_page) from query params with safe defaults."""
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = max(1, int(request.GET.get("per_page", DEFAULT_RECORDS_PER_PAGE)))
    except (TypeError, ValueError):
        per_page = DEFAULT_RECORDS_PER_PAGE
    if per_page not in (25, 50, 100, 200):
        per_page = DEFAULT_RECORDS_PER_PAGE
    return page, per_page


def _build_search_clause(database: Database, columns: list[str], q: str) -> tuple[str, list[Any]]:
    """Return a (WHERE clause string, params list) for a keyword search across columns."""
    if not q or not columns:
        return "", []
    pattern = f"%{q}%"
    conditions = []
    params = []
    for col in columns:
        col_q = quote_identifier(database, col)
        if database.provider == Database.POSTGRESQL:
            conditions.append(f"CAST({col_q} AS TEXT) ILIKE %s")
        elif database.provider == Database.MARIADB_MYSQL:
            conditions.append(f"CAST({col_q} AS CHAR) LIKE %s")
        else:
            conditions.append(f"CAST({col_q} AS TEXT) LIKE %s")
        params.append(pattern)
    return " WHERE " + " OR ".join(conditions), params


def _count_filtered_rows(database: Database, table_name: str, columns: list[str], q: str) -> int:
    """Return total rows matching the search filter."""
    where_clause, params = _build_search_clause(database, columns, q)
    conn = open_connection(database)
    try:
        cursor = conn.cursor()
        query = f"SELECT COUNT(*) FROM {quote_identifier(database, table_name)}{where_clause}"
        if database.provider == Database.POSTGRESQL:
            cursor.execute(query, params)
        elif database.provider == Database.MARIADB_MYSQL:
            cursor.execute(query, params)
        else:
            cursor.execute(query, params)
        return cursor.fetchone()[0]
    except Exception as e:
        raise DatabaseQueryError(str(e)) from e
    finally:
        conn.close()


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


def _sidebar_pagination_context(request: HttpRequest, all_tables: list[str]) -> dict:
    """Return pagination context for the sidebar table list."""
    q = request.GET.get("q", "").strip()
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    page_tables, page, total_pages = _paginate_tables(all_tables, page, q)
    return {
        "all_tables": all_tables,
        "sidebar_tables": page_tables,
        "sidebar_page": page,
        "sidebar_total_pages": total_pages,
        "sidebar_q": q,
    }


@login_required
def database_detail(request: HttpRequest, public_id: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)
    context = {
        "database": database,
        "provider_label": dict(Database.PROVIDER_CHOICES).get(database.provider, database.provider),
    }

    try:
        all_tables = list_tables(database)
        context["tables"] = all_tables
        context["schema_json"] = json.dumps(_build_schema(database))
        context["error"] = None
        if database.status != Database.CONNECTED:
            database.status = Database.CONNECTED
            database.save(update_fields=["status"])
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        all_tables = []
        context["tables"] = []
        context["schema_json"] = "{}"
        context["error"] = str(e)
        if database.status != Database.DISCONNECTED:
            database.status = Database.DISCONNECTED
            database.save(update_fields=["status"])
        context.update(_sidebar_pagination_context(request, all_tables))
        return render(request, "Databases/database_detail.html", context)

    context.update(_sidebar_pagination_context(request, all_tables))

    active_table = request.GET.get("table", "") or (all_tables[0] if all_tables else "")
    record_page, record_per_page = _parse_records_pagination(request)
    search_q = request.GET.get("q", "").strip()
    if active_table:
        if active_table in all_tables:
            try:
                offset = (record_page - 1) * record_per_page
                column_names = [c[0] for c in get_columns(database, active_table)]
                where_clause, search_params = _build_search_clause(database, column_names, search_q)
                query = f"SELECT * FROM {quote_identifier(database, active_table)}{where_clause} LIMIT {record_per_page} OFFSET {offset}"
                columns, rows = run_query_with_params(database, query, search_params)
                total_rows = _count_filtered_rows(database, active_table, column_names, search_q)
                context["query"] = query
                context["columns"] = columns
                context["rows"] = rows
                context["active_table"] = active_table
                pk_col = get_primary_key(database, active_table)
                context["pk_column"] = pk_col
                context["pk_index"] = columns.index(pk_col) if pk_col and pk_col in columns else None
                context["sort_column"] = ""
                context["sort_dir"] = "asc"
                context["record_page"] = record_page
                context["record_per_page"] = record_per_page
                context["record_total_pages"] = max(1, (total_rows + record_per_page - 1) // record_per_page)
                context["search_q"] = search_q
            except (DatabaseQueryError, UnsupportedProviderError) as e:
                context["query"] = f"SELECT * FROM {quote_identifier(database, active_table)} LIMIT {record_per_page} OFFSET 0"
                context["columns"] = []
                context["rows"] = []
                context["error"] = str(e)
                context["active_table"] = active_table
                context["pk_column"] = None
                context["pk_index"] = None
                context["sort_column"] = ""
                context["sort_dir"] = "asc"
                context["record_page"] = record_page
                context["record_per_page"] = record_per_page
                context["record_total_pages"] = 1
                context["search_q"] = search_q
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
        all_tables = list_tables(database)
        context["tables"] = all_tables
        context["error"] = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        all_tables = []
        context["tables"] = []
        context["error"] = str(e)

    context.update(_sidebar_pagination_context(request, all_tables))
    return render(request, "sidebar.html", context)


@login_required
def sidebar_tables(request: HttpRequest, public_id: str) -> HttpResponse:
    """HTMX endpoint returning just the paginated table list for the sidebar."""
    database = _get_database_or_404(request, public_id)
    context = {
        "database": database,
        "provider_label": dict(Database.PROVIDER_CHOICES).get(database.provider, database.provider),
        "active_table": request.GET.get("table", "").strip(),
    }

    try:
        all_tables = list_tables(database)
        context["tables"] = all_tables
        context["error"] = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        all_tables = []
        context["tables"] = []
        context["error"] = str(e)

    context.update(_sidebar_pagination_context(request, all_tables))
    return render(request, "Databases/partials/sidebar_table_list.html", context)


@login_required
def table_query(request: HttpRequest, public_id: str, table_name: str) -> HttpResponse:
    database = _get_database_or_404(request, public_id)

    try:
        tables = list_tables(database)
        if table_name not in tables:
            return HttpResponse(f"Table {table_name!r} does not exist.", status=404)

        query = f"SELECT * FROM {quote_identifier(database, table_name)} LIMIT 100"
        columns, rows = run_query(database, query)
        error = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        query = f"SELECT * FROM {quote_identifier(database, table_name)} LIMIT 100"
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
    record_page, record_per_page = _parse_records_pagination(request)
    search_q = request.GET.get("q", "").strip()

    try:
        tables = list_tables(database)
        if table_name not in tables:
            return HttpResponse(f"Table {table_name!r} does not exist.", status=404)

        column_names = [c[0] for c in get_columns(database, table_name)]
        if sort_column and sort_column not in column_names:
            sort_column = ""

        order_clause = ""
        if sort_column:
            order_clause = f" ORDER BY {quote_identifier(database, sort_column)} {sort_dir.upper()}"

        where_clause, search_params = _build_search_clause(database, column_names, search_q)
        offset = (record_page - 1) * record_per_page
        query = f"SELECT * FROM {quote_identifier(database, table_name)}{where_clause}{order_clause} LIMIT {record_per_page} OFFSET {offset}"
        columns, rows = run_query_with_params(database, query, search_params)
        total_rows = _count_filtered_rows(database, table_name, column_names, search_q)
        error = None
    except (DatabaseQueryError, UnsupportedProviderError) as e:
        query = f"SELECT * FROM {quote_identifier(database, table_name)}{where_clause}{order_clause} LIMIT {record_per_page} OFFSET {offset}"
        columns, rows = [], []
        total_rows = 0
        error = str(e)

    record_total_pages = max(1, (total_rows + record_per_page - 1) // record_per_page)

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
        "record_page": record_page,
        "record_per_page": record_per_page,
        "record_total_pages": record_total_pages,
        "search_q": search_q,
    }
    template = "Databases/partials/query_results.html"
    if request.GET.get("partial") == "table":
        template = "Databases/partials/query_results_table.html"
    return render(request, template, context)


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
