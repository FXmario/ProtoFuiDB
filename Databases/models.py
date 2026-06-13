from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from core.models import AbstractModel


class Provider(AbstractModel):
    pass


class Database(AbstractModel):
    name = models.CharField(db_index=True)
    user = models.CharField(db_index=True)
    password = models.CharField(max_length=128)
    host = models.CharField()

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
