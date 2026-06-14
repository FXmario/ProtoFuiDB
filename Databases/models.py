from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from core.models import AbstractModel


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
    user = models.CharField(db_index=True, max_length=255)
    password = models.TextField()
    host = models.CharField(max_length=255)
    port = models.IntegerField()
    provider = models.CharField(
        max_length=50,
        choices=PROVIDER_CHOICES,
        default=POSTGRESQL,
    )

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
