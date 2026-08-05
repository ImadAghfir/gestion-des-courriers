from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        INFO = "info", "Information"
        WARNING = "warning", "Avertissement"
        URGENT = "urgent", "Urgent"

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    courrier = models.ForeignKey(
        "courriers.Courrier",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    message = models.TextField()
    type = models.CharField(
        max_length=10,
        choices=Type.choices,
        default=Type.INFO,
    )
    lu = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.destinataire.username}"