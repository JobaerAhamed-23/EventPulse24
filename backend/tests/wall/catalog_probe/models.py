from django.db import models

from shared.retention import RetentionCategory


class Thing(models.Model):
    retention_category = RetentionCategory.NOT_USER_DATA

    name = models.CharField(max_length=50)
