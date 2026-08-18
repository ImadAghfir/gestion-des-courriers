"""
Alertes automatiques sur les échéances — cahier des charges §5.9.

- « Date limite approche (J-2) » → responsable du courrier, priorité haute ;
- « Courrier en retard »        → DG + Chef de Département, prioritaire.

La fonction `verifier_echeances` est appelée :
- par la commande `python manage.py verifier_echeances` (planifiable) ;
- automatiquement (au plus une fois par heure) quand un utilisateur
  consulte ses notifications.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from courriers.models import Courrier

from .models import Notification

#: Statuts pour lesquels plus aucune alerte n'est utile.
#:
#: - `traite` / `archive` : le traitement du courrier entrant est terminé ;
#: - `rejete` : le courrier est renvoyé au Bureau d'Ordre pour correction ;
#: - `envoye` : un courrier sortant déjà expédié n'a plus d'échéance à tenir
#:   (seul l'archivage reste, qui est une opération de classement).
STATUTS_TERMINES = ("traite", "archive", "rejete", "envoye")

#: Durée de conservation des notifications déjà lues (en jours).
CONSERVATION_NOTIFICATIONS_LUES = 90

MARQUEUR_J2 = "[Rappel J-2]"
MARQUEUR_RETARD = "[RETARD]"


def _deja_notifie_aujourd_hui(courrier, destinataire, marqueur):
    """Évite les doublons : une seule alerte par jour, par courrier et par personne."""
    aujourd_hui = timezone.now().date()
    return Notification.objects.filter(
        courrier=courrier,
        destinataire=destinataire,
        message__startswith=marqueur,
        date__date=aujourd_hui,
    ).exists()


def _notifier_unique(courrier, destinataire, message, type_notification, marqueur):
    if destinataire is None or not destinataire.is_active:
        return 0
    if _deja_notifie_aujourd_hui(courrier, destinataire, marqueur):
        return 0
    Notification.objects.create(
        destinataire=destinataire,
        courrier=courrier,
        message=message,
        type=type_notification,
    )
    return 1


def _responsables_courrier(courrier):
    """
    Destinataires du rappel J-2 : le responsable actuel du courrier.

    - Si un service est affecté → Chef(s) de Service de ce service ;
    - sinon si un département est affecté → Chef(s) de ce département ;
    - sinon → le créateur (Bureau d'Ordre).
    """
    User = get_user_model()
    if courrier.service_id:
        cibles = list(
            User.objects.filter(
                is_active=True, role="chef_service", service_id=courrier.service_id
            )
        )
        if cibles:
            return cibles
    if courrier.departement_id:
        cibles = list(
            User.objects.filter(
                is_active=True,
                role="chef_departement",
                departement_id=courrier.departement_id,
            )
        )
        if cibles:
            return cibles
    return [courrier.createur]


def verifier_echeances():
    """
    Parcourt les courriers non terminés ayant une date limite et crée
    les alertes nécessaires. Retourne (nb_rappels_j2, nb_alertes_retard).
    """
    User = get_user_model()
    aujourd_hui = timezone.now().date()

    courriers = Courrier.objects.filter(
        date_echeance__isnull=False
    ).exclude(statut__in=STATUTS_TERMINES).select_related(
        "departement", "service", "createur"
    )

    rappels = 0
    retards = 0
    dgs = list(User.objects.filter(is_active=True, role__in=["dg", "secretaire"]))

    for courrier in courriers:
        echeance = courrier.date_echeance

        # --- Courrier en retard → DG + Chef de Département (prioritaire)
        if echeance < aujourd_hui:
            jours_retard = (aujourd_hui - echeance).days
            message = (
                f"{MARQUEUR_RETARD} Le courrier {courrier.numero} – "
                f"« {courrier.objet} » a dépassé sa date limite du "
                f"{echeance:%d/%m/%Y} ({jours_retard} jour(s) de retard)."
            )
            destinataires = list(dgs)
            if courrier.departement_id:
                destinataires += list(
                    User.objects.filter(
                        is_active=True,
                        role="chef_departement",
                        departement_id=courrier.departement_id,
                    )
                )
            for destinataire in destinataires:
                retards += _notifier_unique(
                    courrier, destinataire, message,
                    Notification.Type.URGENT, MARQUEUR_RETARD,
                )

        # --- Date limite qui approche (J-2) → responsable du courrier (haute)
        elif echeance <= aujourd_hui + timedelta(days=2):
            jours_restants = (echeance - aujourd_hui).days
            if jours_restants == 0:
                delai = "aujourd'hui"
            elif jours_restants == 1:
                delai = "demain"
            else:
                delai = f"dans {jours_restants} jours"
            message = (
                f"{MARQUEUR_J2} La date limite du courrier {courrier.numero} – "
                f"« {courrier.objet} » arrive à échéance {delai} "
                f"({echeance:%d/%m/%Y})."
            )
            for destinataire in _responsables_courrier(courrier):
                rappels += _notifier_unique(
                    courrier, destinataire, message,
                    Notification.Type.WARNING, MARQUEUR_J2,
                )

    return rappels, retards


def purger_notifications_lues(jours=None):
    """
    Supprime les notifications déjà lues au-delà de la durée de conservation.

    Les notifications non lues ne sont jamais supprimées : l'utilisateur
    doit pouvoir les consulter, quelle que soit leur ancienneté.
    Retourne le nombre de notifications supprimées.
    """
    jours = jours if jours is not None else CONSERVATION_NOTIFICATIONS_LUES
    limite = timezone.now() - timedelta(days=jours)

    supprimees, _ = Notification.objects.filter(lu=True, date__lt=limite).delete()
    return supprimees
