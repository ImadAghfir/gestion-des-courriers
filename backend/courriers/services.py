"""
Service métier pour la gestion des courriers.

Toutes les règles métier sont centralisées ici. Les vues et le frontend
ne font que déclencher des actions — jamais implémenter la logique.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from historique.models import Historique
from notifications.models import Notification


# ---------------------------------------------------------------------------
# Machine à états : transitions autorisées par type de courrier
# ---------------------------------------------------------------------------

#: Courrier entrant :  RECU → AFFECTE → EN_COURS ↔ EN_ATTENTE → TRAITE → ARCHIVE
TRANSITIONS_ENTRANT = {
    "recu":       ["affecte", "en_cours"],  # en_cours : affectation directe possible
    "affecte":    ["en_cours"],
    "en_cours":   ["traite", "en_attente"],
    "en_attente": ["en_cours"],             # retour possible vers EN_COURS uniquement
    "traite":     ["archive"],              # archivage seulement depuis TRAITE
}

#: Courrier sortant : BROUILLON → EN_VALIDATION → VALIDE → ENVOYE → ARCHIVE
TRANSITIONS_SORTANT = {
    "brouillon":     ["en_validation"],
    "en_validation": ["valide", "brouillon"],  # brouillon = renvoi en correction
    "valide":        ["envoye"],
    "envoye":        ["archive"],
}


def _get_transitions(courrier):
    """Retourne la table de transitions correspondant au type du courrier."""
    if courrier.type_courrier == "entrant":
        return TRANSITIONS_ENTRANT
    return TRANSITIONS_SORTANT


def verifier_transition(courrier, nouveau_statut):
    """
    Vérifie qu'une transition de statut est valide.
    Lève ValidationError si la transition est interdite.
    """
    transitions = _get_transitions(courrier)
    autorisees = transitions.get(courrier.statut, [])
    if nouveau_statut not in autorisees:
        type_label = courrier.get_type_courrier_display()
        raise ValidationError(
            f"Transition interdite pour un {type_label} : "
            f"'{courrier.statut}' → '{nouveau_statut}'. "
            f"Statuts autorisés depuis '{courrier.statut}' : {autorisees or ['aucun']}."
        )


def get_statuts_suivants(courrier):
    """
    Retourne la liste des statuts atteignables depuis l'état actuel.
    Utile pour construire les actions disponibles dans l'API.
    """
    transitions = _get_transitions(courrier)
    return transitions.get(courrier.statut, [])


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notifier_responsable_si_urgent(courrier, declencheur=None):
    """
    Notifie le responsable du service si le courrier est URGENT ou TRÈS URGENT.
    N'envoie pas de doublon si le responsable est lui-même le déclencheur.
    """
    if courrier.priorite not in ("urgent", "tres_urgent"):
        return

    service = courrier.service
    if not service or not service.responsable:
        return

    responsable = service.responsable
    if declencheur and declencheur.pk == responsable.pk:
        return  # pas de notification redondante

    priorite_label = "URGENT" if courrier.priorite == "urgent" else "TRÈS URGENT"
    Notification.objects.create(
        destinataire=responsable,
        courrier=courrier,
        message=(
            f"[{priorite_label}] Le courrier {courrier.numero} – "
            f"« {courrier.objet} » requiert votre attention immédiate."
        ),
        type=Notification.Type.URGENT,
    )


# ---------------------------------------------------------------------------
# Actions métier
# ---------------------------------------------------------------------------

@transaction.atomic
def changer_statut(courrier, nouveau_statut, auteur, commentaire=""):
    """
    Change le statut d'un courrier après validation de la machine à états.

    - Vérifie que la transition est autorisée.
    - Sauvegarde le nouveau statut.
    - Trace l'action dans Historique.

    Retourne le courrier mis à jour.
    """
    verifier_transition(courrier, nouveau_statut)

    ancien_statut = courrier.get_statut_display()
    courrier.statut = nouveau_statut
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.CHANGEMENT_STATUT,
        commentaire=commentaire or (
            f"Statut mis à jour : {ancien_statut} → {courrier.get_statut_display()}."
        ),
    )

    return courrier


@transaction.atomic
def affecter_courrier(
    courrier, auteur,
    utilisateur_cible=None, service_cible=None,
    commentaire=""
):
    """
    Affecte un courrier à un utilisateur ou un service.

    Règles appliquées :
    - Au moins une cible (utilisateur ou service) est obligatoire.
    - Si le courrier est RECU, il passe automatiquement à AFFECTE.
    - Crée une ligne Affectation, une ligne Historique et une Notification.
    - Notifie immédiatement le responsable si le courrier est urgent / très urgent.

    Retourne l'Affectation créée.
    """
    from affectations.models import Affectation

    if not utilisateur_cible and not service_cible:
        raise ValidationError(
            "Une affectation doit cibler un utilisateur ou un service."
        )

    # Passage automatique RECU → AFFECTE
    if courrier.statut == "recu":
        courrier.statut = "affecte"
        courrier.save(update_fields=["statut"])

    affectation = Affectation.objects.create(
        courrier=courrier,
        auteur=auteur,
        utilisateur=utilisateur_cible,
        service=service_cible,
        commentaire=commentaire,
    )

    # Libellé de la cible pour les messages
    if utilisateur_cible:
        cible_label = utilisateur_cible.get_full_name() or utilisateur_cible.username
    else:
        cible_label = f"service {service_cible.nom}"

    # Historique
    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.AFFECTATION,
        commentaire=(
            f"Affecté à {cible_label}."
            + (f" Note : {commentaire}" if commentaire else "")
        ),
    )

    # Notification → utilisateur cible
    if utilisateur_cible:
        Notification.objects.create(
            destinataire=utilisateur_cible,
            courrier=courrier,
            message=(
                f"Le courrier {courrier.numero} – « {courrier.objet} » "
                f"vous a été affecté par {auteur.get_full_name() or auteur.username}."
            ),
            type=(
                Notification.Type.URGENT
                if courrier.priorite in ("urgent", "tres_urgent")
                else Notification.Type.INFO
            ),
        )

    # Notification → responsable du service cible (différent du créateur)
    if service_cible and service_cible.responsable:
        responsable = service_cible.responsable
        if responsable.pk != auteur.pk:
            Notification.objects.create(
                destinataire=responsable,
                courrier=courrier,
                message=(
                    f"Le courrier {courrier.numero} – « {courrier.objet} » "
                    f"a été affecté au {cible_label}."
                ),
                type=Notification.Type.INFO,
            )

    # Alerte immédiate si urgent / très urgent
    notifier_responsable_si_urgent(courrier, declencheur=auteur)

    return affectation


@transaction.atomic
def valider_courrier(courrier, auteur, commentaire=""):
    """
    Valide un courrier sortant (EN_VALIDATION → VALIDE).

    Seule la machine à états décide si la transition est possible.
    La vérification du rôle reste dans la vue.
    """
    courrier = changer_statut(
        courrier,
        nouveau_statut="valide",
        auteur=auteur,
        commentaire=commentaire or "Courrier validé.",
    )

    # Trace explicite de validation
    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.VALIDATION,
        commentaire=commentaire or "Courrier sortant validé.",
    )

    return courrier


@transaction.atomic
def ajouter_commentaire(courrier, auteur, commentaire):
    """
    Ajoute un commentaire libre sur un courrier, tracé dans Historique.
    Le commentaire ne peut pas être vide.
    """
    if not commentaire or not commentaire.strip():
        raise ValidationError("Le commentaire ne peut pas être vide.")

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.COMMENTAIRE,
        commentaire=commentaire.strip(),
    )


@transaction.atomic
def ajouter_document(courrier, auteur, fichier):
    """
    Attache ou remplace le fichier d'un courrier et trace l'action dans Historique.
    """
    courrier.fichier = fichier
    courrier.save(update_fields=["fichier"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.DOCUMENT_AJOUTE,
        commentaire=f"Document ajouté : {fichier.name}.",
    )
