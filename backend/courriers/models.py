from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Courrier(models.Model):
    class TypeCourrier(models.TextChoices):
        ENTRANT = "entrant", "Courrier entrant"
        SORTANT = "sortant", "Courrier sortant"

    class Priorite(models.TextChoices):
        NORMAL = "normal", "Normal"
        URGENT = "urgent", "Urgent"
        TRES_URGENT = "tres_urgent", "Tres urgent"

    class Statut(models.TextChoices):
        RECU = "recu", "Reçu"
        AFFECTE = "affecte", "Affecté"
        EN_COURS = "en_cours", "En cours"
        EN_ATTENTE = "en_attente", "En attente"
        TRAITE = "traite", "Traité"
        ARCHIVE = "archive", "Archivé"
        BROUILLON = "brouillon", "Brouillon"
        EN_VALIDATION = "en_validation", "En validation"
        VALIDE = "valide", "Validé"
        ENVOYE = "envoye", "Envoyé"

    numero = models.CharField(max_length=20, unique=True, blank=True)
    type_courrier = models.CharField(
        max_length=10,
        choices=TypeCourrier.choices,
    )
    objet = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    expediteur = models.CharField(max_length=255, blank=True)
    destinataire = models.CharField(max_length=255, blank=True)
    categorie = models.CharField(max_length=100)
    priorite = models.CharField(
        max_length=20,
        choices=Priorite.choices,
        default=Priorite.NORMAL,
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        blank=True,
    )
    date_reception = models.DateField(null=True, blank=True)
    date_envoi_prevue = models.DateField(null=True, blank=True)
    date_echeance = models.DateField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    fichier = models.FileField(upload_to="courriers/", null=True, blank=True)
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers",
    )
    createur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="courriers_crees",
    )

    class Meta:
        ordering = ["-date_creation"]

    # ------------------------------------------------------------------
    # Règles métier au niveau modèle (deuxième barrière après le service)
    # ------------------------------------------------------------------

    def clean(self):
        """
        Validation au niveau modèle.

        Ces contrôles doublent le service Python pour garantir l'intégrité
        même en cas d'accès direct à l'ORM (shell, scripts de migration…).
        """
        # Règle : numéro immuable après création
        if self.pk:
            try:
                original = Courrier.objects.get(pk=self.pk)
                if original.numero and self.numero != original.numero:
                    raise ValidationError(
                        {"numero": "Le numéro d'un courrier ne peut pas être modifié après sa création."}
                    )
            except Courrier.DoesNotExist:
                pass

        # Règle : un courrier entrant ne peut être archivé que depuis TRAITE
        if (
            self.pk
            and self.type_courrier == self.TypeCourrier.ENTRANT
            and self.statut == self.Statut.ARCHIVE
        ):
            try:
                original = Courrier.objects.get(pk=self.pk)
                if original.statut != self.Statut.TRAITE:
                    raise ValidationError(
                        {"statut": "Un courrier entrant ne peut être archivé que s'il est traité."}
                    )
            except Courrier.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        # Génération automatique du numéro à la création uniquement
        if not self.numero:
            annee = timezone.now().year
            prefixe = "CE" if self.type_courrier == self.TypeCourrier.ENTRANT else "CS"
            dernier = Courrier.objects.filter(
                numero__startswith=f"{prefixe}-{annee}-"
            ).order_by("-numero").first()

            sequence = int(dernier.numero.split("-")[-1]) + 1 if dernier else 1
            self.numero = f"{prefixe}-{annee}-{sequence:05d}"

        # Statut initial par défaut
        if not self.statut:
            self.statut = (
                self.Statut.RECU
                if self.type_courrier == self.TypeCourrier.ENTRANT
                else self.Statut.BROUILLON
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} - {self.objet}"