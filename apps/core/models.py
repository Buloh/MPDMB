"""Sdílené datové struktury jádra MPDMB."""

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Auditní záznam důležité změny v systému."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name="uživatel",
    )
    created_at = models.DateTimeField("čas", auto_now_add=True, db_index=True)
    operation = models.CharField("operace", max_length=64)
    object_type = models.CharField("typ objektu", max_length=128)
    object_id = models.CharField("identifikátor objektu", max_length=64)
    detail = models.TextField("detail", blank=True)

    class Meta:
        verbose_name = "auditní událost"
        verbose_name_plural = "auditní události"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.operation} {self.object_type}:{self.object_id}"
