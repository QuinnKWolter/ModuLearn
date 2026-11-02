from django.db import models

from django.conf import settings


class TranslationReport(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('resolved', 'Resolved'), ('ignored', 'Ignored')]
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    language = models.CharField(max_length=16)
    page_path = models.CharField(max_length=500)
    original_text = models.TextField(max_length=1000)
    suggestion = models.TextField(max_length=2000, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open', db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.language}: {self.original_text[:80]}'
