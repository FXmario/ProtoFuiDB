from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from Databases.models import Database
from Databases.forms import DatabaseForm

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