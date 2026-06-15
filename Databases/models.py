from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from core.models import AbstractModel


def database_file_upload_path(instance, filename):
    return f"databases/{instance.public_id}/{filename}"


class Database(AbstractModel):
    POSTGRESQL = "django.db.backends.postgresql"
    MARIADB_MYSQL = "django.db.backends.mysql"
    SQLITE3 = "django.db.backends.sqlite3"
    PROVIDER_CHOICES = [
        (POSTGRESQL, "PostgreSQL"),
        (MARIADB_MYSQL, "MariaDB/MySQL"),
        (SQLITE3, "SQLite3"),
    ]

    name = models.CharField(db_index=True, max_length=255)
    db_name = models.CharField(db_index=True, max_length=255, default="")
    user = models.CharField(db_index=True, max_length=255, blank=True, default="")
    password = models.TextField(blank=True, default="")
    host = models.CharField(max_length=255, blank=True, default="")
    port = models.IntegerField(blank=True, null=True)
    provider = models.CharField(
        max_length=50,
        choices=PROVIDER_CHOICES,
        default=POSTGRESQL,
    )
    file = models.FileField(
        upload_to=database_file_upload_path,
        blank=True,
        null=True,
        help_text="Upload a .db file (required for SQLite3).",
    )

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
