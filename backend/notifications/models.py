from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        INFO = "info", "Information"
        WARNING = "warning", "Avertissement"
        URGENT = "urgent", "Urgent"

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    courrier = models.ForeignKey(
        "courriers.Courrier",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    message = models.TextField()
    type = models.CharField(
        max_length=10,
        choices=Type.choices,
        default=Type.INFO,
    )
    lu = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.destinataire.username}"


class ControleEcheances(models.Model):
    """
    Horodatage du dernier contrôle automatique des échéances (§5.9).

    Permet de lancer la vérification J-2 / retard au plus une fois par
    intervalle, quel que soit le nombre d'utilisateurs connectés.
    """

    dernier_controle = models.DateTimeField()

    class Meta:
        verbose_name = "Contrôle des échéances"

    @classmethod
    def doit_executer(cls, intervalle_minutes=60):
        """
        Retourne True (et met à jour l'horodatage) si le dernier contrôle
        date de plus de `intervalle_minutes`. Atomique et idempotent.
        """
        from django.utils import timezone

        maintenant = timezone.now()
        seuil = maintenant - timezone.timedelta(minutes=intervalle_minutes)

        controle, cree = cls.objects.get_or_create(
            pk=1, defaults={"dernier_controle": maintenant}
        )
        if cree:
            return True

        # Mise à jour conditionnelle pour éviter les exécutions simultanées
        mis_a_jour = cls.objects.filter(
            pk=1, dernier_controle__lt=seuil
        ).update(dernier_controle=maintenant)
        return bool(mis_a_jour)