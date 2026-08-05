from django.contrib.auth.models import AbstractUser
from django.db import models


class Utilisateur(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        RESPONSABLE = "responsable", "Responsable"
        AGENT = "agent", "Agent"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.AGENT,
    )
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="utilisateurs",
    )

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"