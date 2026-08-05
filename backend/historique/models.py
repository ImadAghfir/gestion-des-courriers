from django.conf import settings
from django.db import models


class Historique(models.Model):
    class Action(models.TextChoices):
        CREATION = "creation", "Creation"
        MODIFICATION = "modification", "Modification"
        AFFECTATION = "affectation", "Affectation"
        CHANGEMENT_STATUT = "changement_statut", "Changement de statut"
        VALIDATION = "validation", "Validation"
        COMMENTAIRE = "commentaire", "Commentaire"
        DOCUMENT_AJOUTE = "document_ajoute", "Document ajoute"
        CLOTURE = "cloture", "Cloture"

    courrier = models.ForeignKey(
        "courriers.Courrier",
        on_delete=models.CASCADE,
        related_name="historiques",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="actions_historique",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    commentaire = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.courrier.numero} - {self.get_action_display()}"