from django import forms
from django.core.validators import RegexValidator

from Databases.models import Database

SQLITE3 = Database.SQLITE3


class DatabaseForm(forms.ModelForm):
    raw_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input input-bordered w-full"}),
        label="Password",
        help_text="This password will be encrypted before storage.",
        required=False,
    )

    port = forms.CharField(
        validators=[RegexValidator(r"^\d+$", "Enter a valid port number (digits only).")],
        widget=forms.TextInput(attrs={
            "class": "input input-bordered w-full",
            "inputmode": "numeric",
            "pattern": r"\d+",
            "title": "Enter digits only",
            "placeholder": "5432",
            "oninput": "this.value = this.value.replace(/[^0-9]/g, '').replace(/(\..*?)\..*/g, '$1');",
        }),
        label="Port",
        required=False,
    )

    class Meta:
        model = Database
        fields = ["name", "user", "host", "port", "provider", "file"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "user": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "host": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "provider": forms.Select(attrs={
                "class": "select select-bordered w-full",
                "hx-get": "/databases/new/file-field/",
                "hx-target": "#file-field-container",
                "hx-swap": "innerHTML",
                "hx-trigger": "change",
            }),
            "file": forms.FileInput(attrs={"class": "file-input file-bordered w-full"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        provider = cleaned_data.get("provider")

        if provider == SQLITE3:
            if not cleaned_data.get("file"):
                self.add_error("file", "A database file is required for SQLite3.")
        else:
            if not cleaned_data.get("raw_password"):
                self.add_error("raw_password", "Password is required for this provider.")
            if not cleaned_data.get("user"):
                self.add_error("user", "User is required for this provider.")
            if not cleaned_data.get("host"):
                self.add_error("host", "Host is required for this provider.")
            if not cleaned_data.get("port"):
                self.add_error("port", "Port is required for this provider.")

        return cleaned_data

    def save(self, commit=True):
        db = super().save(commit=False)
        raw_password = self.cleaned_data.get("raw_password")
        if raw_password:
            db.set_password(raw_password)
        if commit:
            db.save()
        return db
