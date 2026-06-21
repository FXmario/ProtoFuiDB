from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.forms import CharField, Form
from django.shortcuts import redirect, render
from django.urls import reverse

from Databases.models import Database

User = get_user_model()


class ChangeUsernameForm(Form):
    new_username = CharField(max_length=150, label="New Username")

    def clean_new_username(self):
        new_username = self.cleaned_data["new_username"]
        if User.objects.filter(username=new_username).exclude(pk=self.user_pk).exists():
            raise ValidationError("A user with this username already exists.")
        return new_username


@login_required
def user_detail(request):
    return render(request, "core/user_detail.html", {"user": request.user})


@login_required
def change_username(request):
    if request.method == "POST":
        form = ChangeUsernameForm(request.POST)
        form.user_pk = request.user.pk
        if form.is_valid():
            request.user.username = form.cleaned_data["new_username"]
            request.user.save()
            return redirect(reverse("user-detail"))
    else:
        form = ChangeUsernameForm()

    return render(request, "core/change_username.html", {"form": form})


class CustomLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = AuthenticationForm

    def dispatch(self, request, *args, **kwargs):
        if not User.objects.exists():
            return redirect(reverse("index"))
        return super().dispatch(request, *args, **kwargs)


def index(request):
    if not User.objects.exists():
        return redirect(reverse("register-superuser"))
    if not request.user.is_authenticated:
        return redirect(reverse("login"))
    databases = Database.objects.filter(owner=request.user)
    return render(request, "Databases/dashboard_index.html", {"databases": databases})


def register_superuser(request):
    if User.objects.exists():
        return redirect(reverse("index"))

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_superuser = True
            user.is_staff = True
            user.save()
            return redirect(reverse("index"))
    else:
        form = UserCreationForm()

    return render(request, "core/register_superuser.html", {"form": form})
