from django.db import models

from core.validators import validate_e164_phone


class Call(models.Model):
    STATUS_CHOICES = [
        ("missed", "Missed"),
        ("answered_by_ai", "Answered by AI"),
        ("completed", "Completed"),
    ]

    caller_number = models.CharField(max_length=30, validators=[validate_e164_phone])
    caller_name = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="missed")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.caller_number} - {self.status}"