"""
Service métier pour la gestion des courriers — cahier des charges v3.3.

Toutes les règles métier (workflow, rôles, notifications, traçabilité)
sont centralisées ici. Les vues ne font que déclencher les actions.

Cycle de vie d'un courrier ENTRANT :
    ENREGISTRE / AFFECT_PROVISOIRE  → TRANSMIS      (Bureau d'Ordre)
    TRANSMIS                        → VALIDE|REJETE (DG)
    REJETE                          → TRANSMIS      (Bureau d'Ordre, après correction)
    VALIDE                          → AFFECTE       (DG : affectation finale)
    AFFECTE                         → RETOURNE_DG   (Chef Dept : erreur d'affectation)
    RETOURNE_DG                     → AFFECTE       (DG : réaffectation)
    AFFECTE                         → EN_TRAITEMENT (Chef de Service)
    EN_TRAITEMENT                   → TRAITE        (Chef de Service : clôture)
    TRAITE                          → ARCHIVE       (Bureau d'Ordre)

Cycle de vie d'un courrier SORTANT :
    ENREGISTRE → VALIDE (DG) → ENVOYE (Bureau d'Ordre) → ARCHIVE (Bureau d'Ordre)
    (rejet possible : ENREGISTRE → REJETE → ENREGISTRE après correction)
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from historique.models import Historique
from notifications.models import Notification

# ---------------------------------------------------------------------------
# Machine à états
# ---------------------------------------------------------------------------

TRANSITIONS_ENTRANT = {
    "enregistre":        ["transmis"],
    "affect_provisoire": ["transmis"],
    "transmis":          ["valide", "rejete"],
    "rejete":            ["transmis"],
    "valide":            ["affecte"],
    "affecte":           ["retourne_dg", "en_traitement"],
    "retourne_dg":       ["affecte"],
    "en_traitement":     ["traite"],
    "traite":            ["archive"],
}

TRANSITIONS_SORTANT = {
    "enregistre": ["valide", "rejete"],
    "rejete":     ["enregistre"],
    "valide":     ["envoye"],
    "envoye":     ["archive"],
}


def _get_transitions(courrier):
    if courrier.type_courrier == "entrant":
        return TRANSITIONS_ENTRANT
    return TRANSITIONS_SORTANT


def verifier_transition(courrier, nouveau_statut):
    """Lève ValidationError si la transition de statut est interdite."""
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
    """Statuts atteignables depuis l'état actuel (pour le frontend)."""
    return _get_transitions(courrier).get(courrier.statut, [])


# ---------------------------------------------------------------------------
# Rôles
# ---------------------------------------------------------------------------

def _role(utilisateur):
    if utilisateur.is_superuser:
        return "admin"
    return getattr(utilisateur, "role", "")


def verifier_role(utilisateur, roles_autorises, action_label):
    """Lève PermissionDenied si l'utilisateur n'a pas l'un des rôles requis."""
    if _role(utilisateur) not in roles_autorises:
        raise PermissionDenied(
            f"Action réservée : {action_label}. Votre rôle ne le permet pas."
        )


# ---------------------------------------------------------------------------
# Helpers notifications
# ---------------------------------------------------------------------------

def _notifier(destinataire, courrier, message, type_notification=None):
    if destinataire is None:
        return
    Notification.objects.create(
        destinataire=destinataire,
        courrier=courrier,
        message=message,
        type=type_notification or Notification.Type.INFO,
    )


def _notifier_role(role, courrier, message, type_notification=None, departement=None, service=None):
    """Notifie tous les utilisateurs actifs d'un rôle donné (filtré par périmètre)."""
    User = get_user_model()
    cibles = User.objects.filter(is_active=True, role=role)
    if departement is not None:
        cibles = cibles.filter(departement=departement)
    if service is not None:
        cibles = cibles.filter(service=service)
    for cible in cibles:
        _notifier(cible, courrier, message, type_notification)


def _type_selon_priorite(courrier, defaut=None):
    if courrier.priorite in ("urgent", "tres_urgent"):
        return Notification.Type.URGENT
    return defaut or Notification.Type.INFO


# ---------------------------------------------------------------------------
# Enregistrement (Bureau d'Ordre)
# ---------------------------------------------------------------------------

@transaction.atomic
def enregistrer_courrier(auteur, donnees_validees):
    """
    Crée un courrier (Bureau d'Ordre uniquement, ou Admin).

    - Numéro interne généré automatiquement.
    - L'affectation provisoire est OPTIONNELLE (règle AP-01) et tracée (AP-05).
    """
    from .models import Courrier

    verifier_role(
        auteur,
        ("bureau_ordre", "admin"),
        "seul le Bureau d'Ordre peut enregistrer un courrier",
    )

    courrier = Courrier(createur=auteur, **donnees_validees)
    courrier.full_clean(exclude=["numero", "statut", "createur"])
    courrier.save()

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.ENREGISTREMENT,
        commentaire=(
            f"Courrier enregistré. N° source : {courrier.numero_source} | "
            f"Date source : {courrier.date_source:%d/%m/%Y}."
        ),
    )

    if courrier.affectation_provisoire:
        Historique.objects.create(
            courrier=courrier,
            auteur=auteur,
            action=Historique.Action.AFFECT_PROVISOIRE,
            commentaire=(
                f"Affectation provisoire proposée → {courrier.affectation_provisoire}."
            ),
        )
        _notifier(
            auteur,
            courrier,
            f"Courrier {courrier.numero} enregistré avec affectation provisoire "
            f"proposée : {courrier.affectation_provisoire}.",
        )

    return courrier


def _notifier_direction(courrier, message, type_notification=None):
    """Notifie le Directeur Général et le Secrétaire (rôle équivalent v4.0)."""
    _notifier_role("dg", courrier, message, type_notification)
    _notifier_role("secretaire", courrier, message, type_notification)


# ---------------------------------------------------------------------------
# Transmission au DG / Secrétaire (Bureau d'Ordre)
# ---------------------------------------------------------------------------

@transaction.atomic
def transmettre_au_dg(courrier, auteur, commentaire=""):
    """ENREGISTRE / AFFECT_PROVISOIRE / REJETE → TRANSMIS. Notifie le DG et le Secrétaire."""
    verifier_role(
        auteur,
        ("bureau_ordre", "admin"),
        "seul le Bureau d'Ordre peut transmettre un courrier au DG / Secrétaire",
    )
    if courrier.type_courrier != "entrant":
        raise ValidationError("Seuls les courriers entrants sont transmis au DG / Secrétaire.")

    verifier_transition(courrier, "transmis")
    courrier.statut = "transmis"
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.TRANSMISSION,
        commentaire=commentaire or "Courrier transmis à la Direction (DG / Secrétaire).",
    )

    _notifier_direction(
        courrier,
        f"Le courrier {courrier.numero} – « {courrier.objet} » vous a été "
        f"transmis par le Bureau d'Ordre pour validation.",
        _type_selon_priorite(courrier),
    )

    return courrier


# ---------------------------------------------------------------------------
# Validation / Rejet (Directeur Général / Secrétaire)
# ---------------------------------------------------------------------------

@transaction.atomic
def valider_courrier(courrier, auteur, commentaire=""):
    """TRANSMIS → VALIDE (entrant) ou ENREGISTRE → VALIDE (sortant). DG / Secrétaire uniquement."""
    verifier_role(
        auteur,
        ("dg", "secretaire", "admin"),
        "seul le Directeur Général ou le Secrétaire peut valider un courrier",
    )

    verifier_transition(courrier, "valide")
    courrier.statut = "valide"
    courrier.save(update_fields=["statut"])

    titre_auteur = "le Secrétaire" if _role(auteur) == "secretaire" else "le Directeur Général"
    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.VALIDATION,
        commentaire=commentaire or f"Courrier validé par {titre_auteur}.",
    )

    _notifier(
        courrier.createur,
        courrier,
        f"Le courrier {courrier.numero} – « {courrier.objet} » a été validé.",
    )

    return courrier


@transaction.atomic
def rejeter_courrier(courrier, auteur, commentaire):
    """TRANSMIS → REJETE. Commentaire OBLIGATOIRE. Retour au Bureau d'Ordre."""
    verifier_role(
        auteur,
        ("dg", "secretaire", "admin"),
        "seul le Directeur Général ou le Secrétaire peut rejeter un courrier",
    )
    if not commentaire or not commentaire.strip():
        raise ValidationError("Un commentaire est obligatoire pour rejeter un courrier.")

    verifier_transition(courrier, "rejete")
    courrier.statut = "rejete"
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.REJET,
        commentaire=commentaire.strip(),
    )

    titre_auteur = "le Secrétaire" if _role(auteur) == "secretaire" else "le DG"
    _notifier(
        courrier.createur,
        courrier,
        f"Le courrier {courrier.numero} – « {courrier.objet} » a été rejeté "
        f"par {titre_auteur}. Motif : {commentaire.strip()}",
        Notification.Type.WARNING,
    )

    return courrier


# ---------------------------------------------------------------------------
# Affectation finale (Directeur Général / Secrétaire) — règles AF-01 à AF-06
# ---------------------------------------------------------------------------

@transaction.atomic
def affectation_finale(courrier, auteur, departement, instructions="", commentaire=""):
    """
    VALIDE → AFFECTE (première affectation) ou RETOURNE_DG → AFFECTE (réaffectation).

    - Le DG et le Secrétaire peuvent l'effectuer (AF-01, CDC v4.0).
    - Choix de n'importe quel département (AF-03), en s'appuyant
      ou non sur l'affectation provisoire (AF-04).
    - Instructions DG/Secrétaire optionnelles, tracées et notifiées.
    - Le Chef de Département concerné est notifié (priorité haute).
    """
    verifier_role(
        auteur,
        ("dg", "secretaire", "admin"),
        "seul le Directeur Général ou le Secrétaire peut effectuer l'affectation finale",
    )
    if departement is None:
        raise ValidationError("Un département est obligatoire pour l'affectation finale.")

    reaffectation = courrier.statut == "retourne_dg"
    verifier_transition(courrier, "affecte")

    courrier.departement = departement
    courrier.service = None  # une (ré)affectation remet le service à zéro
    courrier.statut = "affecte"

    champs = ["departement", "service", "statut"]
    if instructions and instructions.strip():
        courrier.instructions_dg = instructions.strip()
        champs.append("instructions_dg")
    courrier.save(update_fields=champs)

    provisoire = courrier.affectation_provisoire
    suffixe = ""
    if not reaffectation and provisoire:
        suffixe = (
            " (affectation provisoire acceptée)"
            if provisoire.pk == departement.pk
            else f" (affectation provisoire {provisoire} non retenue)"
        )

    titre_auteur = "du Secrétaire" if _role(auteur) == "secretaire" else "du DG"
    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=(
            Historique.Action.REAFFECTATION
            if reaffectation
            else Historique.Action.AFFECT_FINALE
        ),
        commentaire=(
            f"{'Réaffectation' if reaffectation else 'Affectation finale'} "
            f"→ {departement}{suffixe}."
            + (f" Note : {commentaire}" if commentaire else "")
        ),
    )

    if instructions and instructions.strip():
        Historique.objects.create(
            courrier=courrier,
            auteur=auteur,
            action=Historique.Action.INSTRUCTIONS_DG,
            commentaire=instructions.strip(),
        )

    message = (
        f"Le courrier {courrier.numero} – « {courrier.objet} » a été "
        f"{'réaffecté' if reaffectation else 'affecté'} à votre département "
        f"par { 'le Secrétaire' if _role(auteur) == 'secretaire' else 'le Directeur Général'}."
    )
    if instructions and instructions.strip():
        message += f" Des instructions {titre_auteur} sont disponibles."

    _notifier_role(
        "chef_departement",
        courrier,
        message,
        _type_selon_priorite(courrier, Notification.Type.WARNING),
        departement=departement,
    )

    return courrier


@transaction.atomic
def donner_instructions_dg(courrier, auteur, instructions):
    """
    Ajoute ou met à jour les instructions de la Direction (DG / Secrétaire).
    Chaque modification est tracée (RI-05) et notifiée au Chef de Département.
    """
    verifier_role(
        auteur,
        ("dg", "secretaire", "admin"),
        "seules les instructions de direction peuvent être données par le DG ou le Secrétaire",
    )
    if not instructions or not instructions.strip():
        raise ValidationError("Les instructions ne peuvent pas être vides.")
    if courrier.statut in ("traite", "archive"):
        raise ValidationError(
            "Impossible de donner des instructions sur un courrier traité ou archivé."
        )

    ancienne = courrier.instructions_dg
    courrier.instructions_dg = instructions.strip()
    courrier.save(update_fields=["instructions_dg"])

    titre_auteur = "du Secrétaire" if _role(auteur) == "secretaire" else "du DG"
    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.INSTRUCTIONS_DG,
        champ_modifie="instructions_dg",
        ancienne_valeur=ancienne,
        nouvelle_valeur=courrier.instructions_dg,
        commentaire=f"Instructions {titre_auteur} mises à jour." if ancienne else f"Instructions {titre_auteur} ajoutées.",
    )

    if courrier.departement:
        _notifier_role(
            "chef_departement",
            courrier,
            f"Instructions {titre_auteur} reçues pour le courrier {courrier.numero} – "
            f"« {courrier.objet} ».",
            Notification.Type.WARNING,
            departement=courrier.departement,
        )

    return courrier


# ---------------------------------------------------------------------------
# Retour au DG / Secrétaire (Chef de Département) — règles RR-01 à RR-06
# ---------------------------------------------------------------------------

@transaction.atomic
def retourner_au_dg(courrier, auteur, commentaire):
    """
    AFFECTE → RETOURNE_DG. Seul recours du Chef de Département en cas
    d'erreur d'affectation (RR-01). Commentaire OBLIGATOIRE (RR-02),
    notification immédiate et prioritaire au DG et au Secrétaire (RR-03, CDC v4.0).
    """
    verifier_role(
        auteur,
        ("chef_departement", "admin"),
        "seul un Chef de Département peut retourner un courrier au DG / Secrétaire",
    )
    if not commentaire or not commentaire.strip():
        raise ValidationError(
            "Un commentaire est obligatoire pour retourner un courrier au DG / Secrétaire."
        )
    if (
        _role(auteur) == "chef_departement"
        and courrier.departement_id != auteur.departement_id
    ):
        raise PermissionDenied(
            "Vous ne pouvez retourner que les courriers affectés à votre département."
        )

    verifier_transition(courrier, "retourne_dg")
    courrier.statut = "retourne_dg"
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.RETOUR_DG,
        commentaire=commentaire.strip(),
    )

    prefixe = "[URGENT] " if courrier.priorite in ("urgent", "tres_urgent") else ""
    _notifier_direction(
        courrier,
        f"{prefixe}Le courrier {courrier.numero} – « {courrier.objet} » vous a été "
        f"retourné par le Chef de Département "
        f"({auteur.get_full_name() or auteur.username}). "
        f"Motif : {commentaire.strip()}",
        Notification.Type.URGENT,
    )

    return courrier


# ---------------------------------------------------------------------------
# Affectation au service + instructions (Chef de Département)
# ---------------------------------------------------------------------------

@transaction.atomic
def affecter_au_service(courrier, auteur, service, instructions="", commentaire=""):
    """
    Le Chef de Département affecte le courrier à un service de SON département
    uniquement. Instructions optionnelles au Chef de Service.
    """
    verifier_role(
        auteur,
        ("chef_departement", "admin"),
        "seul un Chef de Département peut affecter un courrier à un service",
    )
    if service is None:
        raise ValidationError("Un service est obligatoire pour cette affectation.")
    if courrier.statut != "affecte":
        raise ValidationError(
            "Le courrier doit être affecté (affectation finale du DG) "
            "avant d'être confié à un service."
        )
    if _role(auteur) == "chef_departement":
        if courrier.departement_id != auteur.departement_id:
            raise PermissionDenied(
                "Vous ne pouvez affecter que les courriers de votre département."
            )
    if courrier.departement_id and service.departement_id != courrier.departement_id:
        raise ValidationError(
            "Le service choisi n'appartient pas au département affecté. "
            "Un Chef de Département ne peut pas réaffecter vers un autre "
            "département : utilisez le retour au DG."
        )

    courrier.service = service
    champs = ["service"]
    if instructions and instructions.strip():
        courrier.instructions_chef_dept = instructions.strip()
        champs.append("instructions_chef_dept")
    courrier.save(update_fields=champs)

    from affectations.models import Affectation

    Affectation.objects.create(
        courrier=courrier,
        auteur=auteur,
        service=service,
        commentaire=commentaire,
    )

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.AFFECT_SERVICE,
        commentaire=(
            f"Affecté au service {service}."
            + (f" Note : {commentaire}" if commentaire else "")
        ),
    )

    if instructions and instructions.strip():
        Historique.objects.create(
            courrier=courrier,
            auteur=auteur,
            action=Historique.Action.INSTRUCTIONS_DEPT,
            commentaire=instructions.strip(),
        )

    message = (
        f"Le courrier {courrier.numero} – « {courrier.objet} » a été affecté "
        f"à votre service par le Chef de Département."
    )
    if instructions and instructions.strip():
        message += " Des instructions sont disponibles."

    _notifier_role(
        "chef_service",
        courrier,
        message,
        _type_selon_priorite(courrier, Notification.Type.WARNING),
        service=service,
    )

    return courrier


@transaction.atomic
def donner_instructions_chef_dept(courrier, auteur, instructions):
    """Instructions du Chef de Département (RI-04 : modifiables par lui seul)."""
    verifier_role(
        auteur,
        ("chef_departement", "admin"),
        "seul un Chef de Département peut donner ces instructions",
    )
    if not instructions or not instructions.strip():
        raise ValidationError("Les instructions ne peuvent pas être vides.")
    if (
        _role(auteur) == "chef_departement"
        and courrier.departement_id != auteur.departement_id
    ):
        raise PermissionDenied(
            "Vous ne pouvez donner des instructions que sur les courriers "
            "de votre département."
        )
    if courrier.statut in ("traite", "archive"):
        raise ValidationError(
            "Impossible de donner des instructions sur un courrier traité ou archivé."
        )

    ancienne = courrier.instructions_chef_dept
    courrier.instructions_chef_dept = instructions.strip()
    courrier.save(update_fields=["instructions_chef_dept"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.INSTRUCTIONS_DEPT,
        champ_modifie="instructions_chef_dept",
        ancienne_valeur=ancienne,
        nouvelle_valeur=courrier.instructions_chef_dept,
        commentaire=(
            "Instructions du Chef de Département mises à jour."
            if ancienne
            else "Instructions du Chef de Département ajoutées."
        ),
    )

    if courrier.service:
        _notifier_role(
            "chef_service",
            courrier,
            f"Instructions du Chef de Département reçues pour le courrier "
            f"{courrier.numero} – « {courrier.objet} ».",
            Notification.Type.WARNING,
            service=courrier.service,
        )

    return courrier


# ---------------------------------------------------------------------------
# Traitement et clôture (Chef de Service)
# ---------------------------------------------------------------------------

@transaction.atomic
def traiter_courrier(courrier, auteur, commentaire=""):
    """AFFECTE → EN_TRAITEMENT. Chef de Service du service concerné."""
    verifier_role(
        auteur,
        ("chef_service", "admin"),
        "seul un Chef de Service peut traiter un courrier",
    )
    if _role(auteur) == "chef_service" and courrier.service_id != auteur.service_id:
        raise PermissionDenied(
            "Vous ne pouvez traiter que les courriers affectés à votre service."
        )
    if not courrier.service_id:
        raise ValidationError(
            "Le courrier doit d'abord être affecté à un service par le "
            "Chef de Département."
        )

    verifier_transition(courrier, "en_traitement")
    courrier.statut = "en_traitement"
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.TRAITEMENT,
        commentaire=commentaire or "Prise en charge du courrier — traitement en cours.",
    )

    return courrier


@transaction.atomic
def cloturer_courrier(courrier, auteur, commentaire=""):
    """EN_TRAITEMENT → TRAITE. Notifie le Chef de Département et le DG."""
    verifier_role(
        auteur,
        ("chef_service", "admin"),
        "seul un Chef de Service peut clôturer un courrier",
    )
    if _role(auteur) == "chef_service" and courrier.service_id != auteur.service_id:
        raise PermissionDenied(
            "Vous ne pouvez clôturer que les courriers affectés à votre service."
        )

    verifier_transition(courrier, "traite")
    courrier.statut = "traite"
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.CLOTURE,
        commentaire=commentaire or "Traitement terminé — courrier traité.",
    )

    message = f"Le courrier {courrier.numero} – « {courrier.objet} » a été traité."
    if courrier.departement:
        _notifier_role(
            "chef_departement", courrier, message, departement=courrier.departement
        )
    _notifier_direction(courrier, message)

    return courrier


# ---------------------------------------------------------------------------
# Archivage / Envoi (Bureau d'Ordre)
# ---------------------------------------------------------------------------

@transaction.atomic
def archiver_courrier(courrier, auteur, commentaire=""):
    """TRAITE → ARCHIVE (entrant) ou ENVOYE → ARCHIVE (sortant). Définitif."""
    verifier_role(
        auteur,
        ("bureau_ordre", "admin"),
        "seul le Bureau d'Ordre peut archiver un courrier",
    )

    verifier_transition(courrier, "archive")
    courrier.statut = "archive"
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.ARCHIVAGE,
        commentaire=commentaire or "Courrier classé définitivement en archive.",
    )

    return courrier


@transaction.atomic
def envoyer_courrier(courrier, auteur, commentaire=""):
    """VALIDE → ENVOYE (courrier sortant uniquement)."""
    verifier_role(
        auteur,
        ("bureau_ordre", "admin"),
        "seul le Bureau d'Ordre peut envoyer un courrier sortant",
    )
    if courrier.type_courrier != "sortant":
        raise ValidationError("Seuls les courriers sortants peuvent être envoyés.")

    verifier_transition(courrier, "envoye")
    courrier.statut = "envoye"
    courrier.save(update_fields=["statut"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.ENVOI,
        commentaire=commentaire or "Courrier envoyé au destinataire.",
    )

    return courrier


# ---------------------------------------------------------------------------
# Modification contrôlée (règles RM-01 à RM-06)
# ---------------------------------------------------------------------------

#: Champs immuables — règle RM-01.
CHAMPS_IMMUABLES = (
    "numero", "numero_source", "date_source", "date_reception",
    "date_creation", "createur", "type_courrier", "statut",
)

#: Champs modifiables par rôle (§5.3.7 du cahier des charges).
CHAMPS_MODIFIABLES = {
    "bureau_ordre": (
        "objet", "description", "expediteur", "destinataire", "categorie",
        "priorite", "date_echeance", "fichier", "affectation_provisoire",
    ),
    "dg": ("priorite", "date_echeance"),
    "secretaire": ("priorite", "date_echeance"),
    "chef_departement": (),   # instructions via donner_instructions_chef_dept
    "chef_service": (),       # notes de traitement via commenter
    "admin": (
        "objet", "description", "expediteur", "destinataire", "categorie",
        "priorite", "date_echeance", "fichier", "affectation_provisoire",
        "instructions_dg", "instructions_chef_dept",
        "departement", "service",
    ),
}


def _valeur_lisible(valeur):
    if valeur is None or valeur == "":
        return "—"
    return str(valeur)


@transaction.atomic
def modifier_courrier(courrier, auteur, modifications, commentaire=""):
    """
    Modification contrôlée d'un courrier.

    - Champs immuables refusés (RM-01).
    - Bureau d'Ordre : uniquement avant validation par le DG/Secrétaire (RM-02).
    - DG / Secrétaire : uniquement avant l'affectation au service (RM-03).
    - Chaque champ modifié génère une entrée d'historique conservant
      l'ancienne et la nouvelle valeur (RM-04, RM-05).
    - Le courrier archivé n'est plus modifiable.
    """
    role = _role(auteur)

    if role not in CHAMPS_MODIFIABLES:
        raise PermissionDenied("Votre rôle ne permet pas de modifier un courrier.")

    if courrier.statut == "archive" and role != "admin":
        raise ValidationError("Un courrier archivé ne peut plus être modifié.")

    # Fenêtres de modification par rôle
    if role == "bureau_ordre" and courrier.statut not in courrier.STATUTS_AVANT_VALIDATION:
        raise ValidationError(
            "Le Bureau d'Ordre ne peut plus modifier un courrier "
            "après sa validation par le DG / Secrétaire (règle RM-02)."
        )
    if role in ("dg", "secretaire") and (courrier.service_id or courrier.statut in ("en_traitement", "traite", "archive")):
        raise ValidationError(
            "Le DG ou le Secrétaire ne peut plus modifier un courrier après son affectation "
            "à un service (règle RM-03)."
        )

    champs_autorises = CHAMPS_MODIFIABLES[role]
    entrees = []

    for champ, nouvelle_valeur in modifications.items():
        if champ in CHAMPS_IMMUABLES:
            raise ValidationError(
                f"Le champ « {champ} » est immuable (règle RM-01)."
            )
        if champ not in champs_autorises:
            raise PermissionDenied(
                f"Votre rôle ne permet pas de modifier le champ « {champ} »."
            )

        ancienne_valeur = getattr(courrier, champ)
        if ancienne_valeur == nouvelle_valeur:
            continue

        setattr(courrier, champ, nouvelle_valeur)
        entrees.append((champ, ancienne_valeur, nouvelle_valeur))

    if not entrees:
        return courrier

    courrier.full_clean(exclude=["statut", "createur"])
    courrier.save()

    for champ, ancienne, nouvelle in entrees:
        Historique.objects.create(
            courrier=courrier,
            auteur=auteur,
            action=Historique.Action.MODIFICATION,
            champ_modifie=champ,
            ancienne_valeur=_valeur_lisible(ancienne),
            nouvelle_valeur=_valeur_lisible(nouvelle),
            commentaire=commentaire,
        )

    # Notification à l'utilisateur affecté (tableau §5.9 : « Courrier modifié »)
    champs_label = ", ".join(champ for champ, *_ in entrees)
    message = (
        f"Le courrier {courrier.numero} – « {courrier.objet} » a été modifié "
        f"({champs_label})."
    )
    if courrier.service:
        _notifier_role("chef_service", courrier, message, service=courrier.service)
    elif courrier.departement:
        _notifier_role(
            "chef_departement", courrier, message, departement=courrier.departement
        )

    return courrier


# ---------------------------------------------------------------------------
# Commentaires et documents
# ---------------------------------------------------------------------------

@transaction.atomic
def ajouter_commentaire(courrier, auteur, commentaire):
    """Ajoute un commentaire libre, tracé dans l'historique."""
    if not commentaire or not commentaire.strip():
        raise ValidationError("Le commentaire ne peut pas être vide.")
    if courrier.statut == "archive":
        raise ValidationError("Un courrier archivé ne peut plus être commenté.")

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.COMMENTAIRE,
        commentaire=commentaire.strip(),
    )


@transaction.atomic
def ajouter_document(courrier, auteur, fichier):
    """Attache ou remplace le fichier d'un courrier, tracé dans l'historique."""
    if courrier.statut == "archive":
        raise ValidationError("Un courrier archivé ne peut plus être modifié.")

    courrier.fichier = fichier
    courrier.save(update_fields=["fichier"])

    Historique.objects.create(
        courrier=courrier,
        auteur=auteur,
        action=Historique.Action.DOCUMENT_AJOUTE,
        commentaire=f"Document ajouté : {fichier.name}.",
    )
