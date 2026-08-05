from django.conf import settings
from django.db import models


class ProfilUtilisateur(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        RESPONSABLE = "responsable", "Responsable"
        AGENT = "agent", "Agent"

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profil",
    )
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
        related_name="profils",
    )
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.utilisateur.username} - {self.get_role_display()}"