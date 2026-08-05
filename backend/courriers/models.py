from django.conf import settings
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
        RECU = "recu", "Recu"
        AFFECTE = "affecte", "Affecte"
        EN_COURS = "en_cours", "En cours"
        EN_ATTENTE = "en_attente", "En attente"
        TRAITE = "traite", "Traite"
        ARCHIVE = "archive", "Archive"
        BROUILLON = "brouillon", "Brouillon"
        EN_VALIDATION = "en_validation", "En validation"
        VALIDE = "valide", "Valide"
        ENVOYE = "envoye", "Envoye"

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
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="courriers_crees",
    )

    class Meta:
        ordering = ["-date_creation"]

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            prefixe = "CE" if self.type_courrier == self.TypeCourrier.ENTRANT else "CS"
            dernier = Courrier.objects.filter(
                numero__startswith=f"{prefixe}-{annee}-"
            ).order_by("-numero").first()

            sequence = int(dernier.numero.split("-")[-1]) + 1 if dernier else 1
            self.numero = f"{prefixe}-{annee}-{sequence:05d}"

        if not self.statut:
            self.statut = (
                self.Statut.RECU
                if self.type_courrier == self.TypeCourrier.ENTRANT
                else self.Statut.BROUILLON
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} - {self.objet}"