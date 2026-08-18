from django.conf import settings
from django.db import models


class Historique(models.Model):
    """
    Journal complet des actions sur un courrier (cahier des charges v3.3, §5.6).

    Pour une modification, `champ_modifie`, `ancienne_valeur` et
    `nouvelle_valeur` conservent la trace exacte du changement (règle RM-05).
    """

    class Action(models.TextChoices):
        RECEPTION = "reception", "Réception"
        ENREGISTREMENT = "enregistrement", "Enregistrement"
        AFFECT_PROVISOIRE = "affect_provisoire", "Affectation provisoire"
        TRANSMISSION = "transmission", "Transmission au DG"
        VALIDATION = "validation", "Validation"
        REJET = "rejet", "Rejet"
        AFFECT_FINALE = "affect_finale", "Affectation finale"
        INSTRUCTIONS_DG = "instructions_dg", "Instructions du DG"
        RETOUR_DG = "retour_dg", "Retour au DG"
        REAFFECTATION = "reaffectation", "Réaffectation"
        AFFECT_SERVICE = "affect_service", "Affectation au service"
        INSTRUCTIONS_DEPT = "instructions_dept", "Instructions du Chef de Département"
        TRAITEMENT = "traitement", "Traitement"
        CLOTURE = "cloture", "Clôture"
        ARCHIVAGE = "archivage", "Archivage"
        ENVOI = "envoi", "Envoi"
        MODIFICATION = "modification", "Modification"
        COMMENTAIRE = "commentaire", "Commentaire"
        DOCUMENT_AJOUTE = "document_ajoute", "Document ajouté"
        CHANGEMENT_STATUT = "changement_statut", "Changement de statut"

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
    champ_modifie = models.CharField(max_length=100, blank=True)
    ancienne_valeur = models.TextField(blank=True)
    nouvelle_valeur = models.TextField(blank=True)
    commentaire = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.courrier.numero} - {self.get_action_display()}"
