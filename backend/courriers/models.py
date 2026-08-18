from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Courrier(models.Model):
    """
    Courrier entrant ou sortant — cahier des charges v3.3.

    Nouveautés v3.3 :
    - numéro source et date source (obligatoires),
    - affectation provisoire (proposée par le Bureau d'Ordre),
    - affectation finale (département officiel choisi par le DG),
    - instructions du DG et du Chef de Département,
    - cycle de vie complet avec retour au DG.
    """

    class TypeCourrier(models.TextChoices):
        ENTRANT = "entrant", "Courrier entrant"
        SORTANT = "sortant", "Courrier sortant"

    class Categorie(models.TextChoices):
        # Courrier entrant
        ADMINISTRATIF = "administratif", "Administratif"
        JURIDIQUE = "juridique", "Juridique"
        FINANCIER = "financier", "Financier"
        # Courrier sortant
        REPONSE = "reponse", "Réponse"
        DEMANDE = "demande", "Demande"
        NOTIFICATION = "notification", "Notification"
        # Commun
        AUTRE = "autre", "Autre"

    class Priorite(models.TextChoices):
        NORMAL = "normal", "Normal"
        URGENT = "urgent", "Urgent"
        TRES_URGENT = "tres_urgent", "Très urgent"

    class Statut(models.TextChoices):
        # Courrier entrant
        ENREGISTRE = "enregistre", "Enregistré"
        AFFECT_PROVISOIRE = "affect_provisoire", "Affectation provisoire proposée"
        TRANSMIS = "transmis", "Transmis au DG"
        VALIDE = "valide", "Validé"
        REJETE = "rejete", "Rejeté"
        AFFECTE = "affecte", "Affecté"
        RETOURNE_DG = "retourne_dg", "Retourné au DG"
        EN_TRAITEMENT = "en_traitement", "En traitement"
        TRAITE = "traite", "Traité"
        ARCHIVE = "archive", "Archivé"
        # Courrier sortant (enregistre → valide → envoye → archive)
        ENVOYE = "envoye", "Envoyé"

    #: Statuts pendant lesquels le Bureau d'Ordre peut encore modifier
    #: le courrier (avant validation par le DG) — règle RM-02.
    STATUTS_AVANT_VALIDATION = ("enregistre", "affect_provisoire", "transmis", "rejete")

    numero = models.CharField(max_length=20, unique=True, blank=True)
    numero_source = models.CharField(
        max_length=100,
        help_text="Numéro figurant sur le document original.",
    )
    date_source = models.DateField(
        help_text="Date figurant sur le document original.",
    )
    type_courrier = models.CharField(
        max_length=10,
        choices=TypeCourrier.choices,
    )
    objet = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    expediteur = models.CharField(max_length=255, blank=True)
    destinataire = models.CharField(max_length=255, blank=True)
    categorie = models.CharField(
        max_length=20,
        choices=Categorie.choices,
        default=Categorie.AUTRE,
    )
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
    date_reception = models.DateField(
        null=True,
        blank=True,
        help_text="Date d'arrivée physique au Bureau d'Ordre (courrier entrant).",
    )
    date_echeance = models.DateField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    fichier = models.FileField(upload_to="courriers/", null=True, blank=True)

    # ---- Affectations (v3.3) -----------------------------------------
    affectation_provisoire = models.ForeignKey(
        "services.Departement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers_proposes",
        help_text="Département probable proposé par le Bureau d'Ordre (non officiel).",
    )
    departement = models.ForeignKey(
        "services.Departement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers",
        help_text="Département officiel (affectation finale par le DG).",
    )
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers",
        help_text="Service officiel de traitement (affecté par le Chef de Département).",
    )

    # ---- Instructions (v3.3) -----------------------------------------
    instructions_dg = models.TextField(
        blank=True,
        help_text="Directives du Directeur Général au Chef de Département.",
    )
    instructions_chef_dept = models.TextField(
        blank=True,
        help_text="Directives du Chef de Département au Chef de Service.",
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
        Contrôles d'intégrité — règle RM-01 : numéro interne, numéro source,
        date source et date de réception sont IMMUABLES.
        """
        if self.pk:
            try:
                original = Courrier.objects.get(pk=self.pk)
            except Courrier.DoesNotExist:
                original = None

            if original:
                if original.numero and self.numero != original.numero:
                    raise ValidationError(
                        {"numero": "Le numéro interne est immuable après création."}
                    )
                if original.numero_source and self.numero_source != original.numero_source:
                    raise ValidationError(
                        {"numero_source": "Le numéro source est immuable après création."}
                    )
                if original.date_source and self.date_source != original.date_source:
                    raise ValidationError(
                        {"date_source": "La date source est immuable après création."}
                    )
                if original.date_reception and self.date_reception != original.date_reception:
                    raise ValidationError(
                        {"date_reception": "La date de réception est immuable après création."}
                    )

                # Un courrier entrant ne peut être archivé que depuis TRAITE
                if (
                    self.type_courrier == self.TypeCourrier.ENTRANT
                    and self.statut == self.Statut.ARCHIVE
                    and original.statut not in (self.Statut.TRAITE, self.Statut.ARCHIVE)
                ):
                    raise ValidationError(
                        {"statut": "Un courrier entrant ne peut être archivé que s'il est traité."}
                    )

    def save(self, *args, **kwargs):
        # Génération automatique du numéro à la création uniquement
        # (CE-2026-00001 pour un entrant, CS-2026-00001 pour un sortant).
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
            if (
                self.type_courrier == self.TypeCourrier.ENTRANT
                and self.affectation_provisoire_id
            ):
                self.statut = self.Statut.AFFECT_PROVISOIRE
            else:
                self.statut = self.Statut.ENREGISTRE

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} - {self.objet}"
