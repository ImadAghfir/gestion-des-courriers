from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Affectation(models.Model):
    courrier = models.ForeignKey(
        "courriers.Courrier",
        on_delete=models.CASCADE,
        related_name="affectations",
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="affectations_recues",
    )
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="affectations_recues",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="affectations_effectuees",
    )
    date = models.DateTimeField(auto_now_add=True)
    commentaire = models.TextField(blank=True)

    def clean(self):
        if not self.utilisateur and not self.service:
            raise ValidationError(
                "Une affectation doit cibler un utilisateur ou un service."
            )

    def __str__(self):
        return f"Affectation de {self.courrier.numero}"