from django.conf import settings
from django.db import models


class Service(models.Model):
    class Statut(models.TextChoices):
        ACTIF = "actif", "Actif"
        INACTIF = "inactif", "Inactif"

    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    statut = models.CharField(
        max_length=10,
        choices=Statut.choices,
        default=Statut.ACTIF,
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services_responsables",
    )

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return f"{self.code} - {self.nom}"