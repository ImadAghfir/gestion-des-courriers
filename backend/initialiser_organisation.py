"""
Script d'initialisation de l'organisation (départements, services, utilisateurs).

Utilisation (depuis le dossier backend, avec le .venv actif) :

    python initialiser_organisation.py

Le script est idempotent : le relancer ne crée pas de doublons.
Modifiez librement les listes DEPARTEMENTS et UTILISATEURS ci-dessous
pour les adapter à votre organisation, puis relancez-le.

⚠️ Tous les comptes sont créés avec le mot de passe par défaut ci-dessous.
   Changez les mots de passe dans l'admin Django (/admin/) après la première
   connexion.
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from services.models import Departement, Service          # noqa: E402
from utilisateurs.models import Utilisateur               # noqa: E402

MOT_DE_PASSE_DEFAUT = "Demo_2026!"

# ---------------------------------------------------------------------------
# Départements et leurs services
# ---------------------------------------------------------------------------

DEPARTEMENTS = [
    {
        "code": "RH",
        "nom": "Ressources Humaines",
        "services": [
            {"code": "RH1", "nom": "Recrutement"},
            {"code": "RH2", "nom": "Administration du personnel"},
        ],
    },
    {
        "code": "FIN",
        "nom": "Finances",
        "services": [
            {"code": "FIN1", "nom": "Comptabilité"},
            {"code": "FIN2", "nom": "Budget"},
        ],
    },
    {
        "code": "TECH",
        "nom": "Technique",
        "services": [
            {"code": "TECH1", "nom": "Informatique"},
            {"code": "TECH2", "nom": "Maintenance"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Utilisateurs : (identifiant, prénom, nom, rôle, code département, code service)
# ---------------------------------------------------------------------------

UTILISATEURS = [
    ("bureau",     "Salma",   "Bennani",  "bureau_ordre",     None,   None),
    ("dg",         "Karim",   "Alaoui",   "dg",               None,   None),
    ("secretaire", "Fatima",  "Zahra",    "secretaire",       None,   None),
    ("chef_rh",    "Nadia",   "Idrissi",  "chef_departement", "RH",   None),
    ("chef_fin",   "Omar",    "Tazi",     "chef_departement", "FIN",  None),
    ("chef_tech",  "Youssef", "Amrani",   "chef_departement", "TECH", None),
    ("chef_rh1",   "Imane",   "Berrada",  "chef_service",     "RH",   "RH1"),
    ("chef_rh2",   "Hicham",  "Fassi",    "chef_service",     "RH",   "RH2"),
    ("chef_fin1",  "Sara",    "Chraibi",  "chef_service",     "FIN",  "FIN1"),
    ("chef_fin2",  "Mehdi",   "Lahlou",   "chef_service",     "FIN",  "FIN2"),
    ("chef_tech1", "Amine",   "Sekkat",   "chef_service",     "TECH", "TECH1"),
    ("chef_tech2", "Layla",   "Ouazzani", "chef_service",     "TECH", "TECH2"),
]


def executer():
    departements = {}
    services = {}

    for donnees in DEPARTEMENTS:
        departement, cree = Departement.objects.get_or_create(
            code=donnees["code"], defaults={"nom": donnees["nom"]}
        )
        departements[donnees["code"]] = departement
        print(f"{'+ créé   ' if cree else '= existant'}  Département {departement}")

        for service_donnees in donnees["services"]:
            service, cree = Service.objects.get_or_create(
                code=service_donnees["code"],
                defaults={"nom": service_donnees["nom"], "departement": departement},
            )
            services[service_donnees["code"]] = service
            print(f"{'+ créé   ' if cree else '= existant'}    Service {service}")

    for identifiant, prenom, nom, role, code_dept, code_service in UTILISATEURS:
        utilisateur, cree = Utilisateur.objects.get_or_create(
            username=identifiant,
            defaults={
                "first_name": prenom,
                "last_name": nom,
                "role": role,
                "departement": departements.get(code_dept),
                "service": services.get(code_service),
            },
        )
        if cree:
            utilisateur.set_password(MOT_DE_PASSE_DEFAUT)
            utilisateur.save()
        print(
            f"{'+ créé   ' if cree else '= existant'}  {identifiant:<12} "
            f"({utilisateur.get_role_display()}"
            f"{' — ' + str(utilisateur.departement) if utilisateur.departement else ''}"
            f"{' / ' + str(utilisateur.service) if utilisateur.service else ''})"
        )

    # Renseigne les responsables des départements et services
    for donnees in DEPARTEMENTS:
        departement = departements[donnees["code"]]
        if not departement.responsable:
            chef = Utilisateur.objects.filter(
                role="chef_departement", departement=departement
            ).first()
            if chef:
                departement.responsable = chef
                departement.save(update_fields=["responsable"])

    for service in services.values():
        if not service.responsable:
            chef = Utilisateur.objects.filter(
                role="chef_service", service=service
            ).first()
            if chef:
                service.responsable = chef
                service.save(update_fields=["responsable"])

    print()
    print("Organisation initialisée avec succès.")
    print(f"Mot de passe par défaut de tous les comptes : {MOT_DE_PASSE_DEFAUT}")
    print("Pensez à changer les mots de passe dans /admin/ !")


if __name__ == "__main__":
    executer()
