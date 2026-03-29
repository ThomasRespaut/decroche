# twilio_bridge/models.py

from django.db import models


class OutboundCall(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("initiated", "Initiated"),
        ("ringing", "Ringing"),
        ("answered", "Answered"),
        ("completed", "Completed"),
        ("busy", "Busy"),
        ("failed", "Failed"),
        ("no-answer", "No Answer"),
        ("canceled", "Canceled"),
    ]

    to_number = models.CharField(max_length=30)
    prospect_name = models.CharField(max_length=255, blank=True)
    company = models.CharField(max_length=255, blank=True)
    custom_prompt = models.TextField(blank=True)

    call_sid = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    duration = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.to_number} ({self.status})"