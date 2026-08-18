from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Utilisateur(AbstractUser):
    """
    Utilisateur de l'application — 5 rôles (cahier des charges v3.3, §4) :
    Administrateur, Bureau d'Ordre, Directeur Général,
    Chef de Département, Chef de Service.

    Sécurité (§10.1) :
    - blocage temporaire après 5 tentatives de connexion échouées ;
    - changement de mot de passe obligatoire à la première connexion.
    """

    #: Nombre de tentatives échouées avant blocage (§10.1).
    MAX_TENTATIVES = 5
    #: Durée du blocage en minutes.
    DUREE_VERROUILLAGE_MINUTES = 15

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        BUREAU_ORDRE = "bureau_ordre", "Bureau d'Ordre"
        DG = "dg", "Directeur Général"
        SECRETAIRE = "secretaire", "Secrétaire"
        CHEF_DEPARTEMENT = "chef_departement", "Chef de Département"
        CHEF_SERVICE = "chef_service", "Chef de Service"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        blank=True,
    )
    departement = models.ForeignKey(
        "services.Departement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="utilisateurs",
    )
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="utilisateurs",
    )

    # ---- Sécurité (§10.1) --------------------------------------------
    tentatives_echouees = models.PositiveIntegerField(
        default=0,
        help_text="Tentatives de connexion échouées consécutives.",
    )
    verrouille_jusqua = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Compte bloqué jusqu'à cette date après 5 échecs.",
    )
    doit_changer_mot_de_passe = models.BooleanField(
        default=True,
        help_text="Changement de mot de passe obligatoire à la première connexion.",
    )

    @property
    def role_effectif(self):
        """Un superutilisateur est toujours traité comme administrateur."""
        if self.is_superuser:
            return self.Role.ADMIN
        return self.role

    @property
    def est_verrouille(self):
        return bool(self.verrouille_jusqua and self.verrouille_jusqua > timezone.now())

    def enregistrer_echec_connexion(self):
        """Incrémente le compteur d'échecs et bloque le compte au 5ᵉ."""
        self.tentatives_echouees += 1
        if self.tentatives_echouees >= self.MAX_TENTATIVES:
            self.verrouille_jusqua = timezone.now() + timezone.timedelta(
                minutes=self.DUREE_VERROUILLAGE_MINUTES
            )
            self.tentatives_echouees = 0
        self.save(update_fields=["tentatives_echouees", "verrouille_jusqua"])

    def reinitialiser_echecs_connexion(self):
        """Remet le compteur à zéro après une connexion réussie."""
        if self.tentatives_echouees or self.verrouille_jusqua:
            self.tentatives_echouees = 0
            self.verrouille_jusqua = None
            self.save(update_fields=["tentatives_echouees", "verrouille_jusqua"])

    def __str__(self):
        return f"{self.username} - {self.get_role_display() or 'sans rôle'}"
