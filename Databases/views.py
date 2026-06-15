from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from Databases.models import Database
from Databases.forms import DatabaseForm
from Databases.utils import check_db_connection

SQLITE3 = Database.SQLITE3


@login_required
def dashboard_index(request: HttpRequest) -> HttpResponse:
    databases = Database.objects.all()
    context = {"databases": databases}
    return render(request, "Databases/dashboard_index.html", context)


@login_required
def database_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = DatabaseForm(request.POST, request.FILES)
        if form.is_valid():
            db = form.save(commit=False)
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