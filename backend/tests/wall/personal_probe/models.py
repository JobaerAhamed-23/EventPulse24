from django.conf import settings
from django.db import models

from shared.retention import RetentionCategory


class Note(models.Model):
    retention_category = RetentionCategory.ACCOUNT_CONTENT

    text = models.CharField(max_length=50)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
