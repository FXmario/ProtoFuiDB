from django.conf import settings
from django.db import models

from core.models import AbstractModel
from Databases.crypto import decrypt, encrypt


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

    UNKNOWN = "unknown"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    STATUS_CHOICES = [
        (UNKNOWN, "Unknown"),
        (CONNECTED, "Connected"),
        (DISCONNECTED, "Disconnected"),
    ]

    SQLGLOT_DIALECTS = {
        POSTGRESQL: "postgres",
        MARIADB_MYSQL: "mysql",
        SQLITE3: "sqlite",
    }

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True
    )
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
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=UNKNOWN,
    )

    def set_password(self, raw_password):
        self.password = encrypt(raw_password)

    def check_password(self, raw_password):
        try:
            return raw_password == decrypt(self.password)
        except Exception:
            return False
