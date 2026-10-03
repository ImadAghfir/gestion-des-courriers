"""
Statistiques et rapports — cahier des charges §5.10.

Accès :
- DG et Admin : statistiques globales ;
- Chef de Département : statistiques de son département uniquement ;
- Autres rôles : accès refusé.
"""
from datetime import date

from django.db.models import Count, F, Q
from django.db.models.functions import TruncMonth

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from courriers.models import Courrier
from historique.models import Historique

STATUTS_OUVERTS_EXCLUS = ("traite", "archive", "rejete")


def _role(utilisateur):
    if utilisateur.is_superuser:
        return "admin"
    return getattr(utilisateur, "role", "")


def _moyenne_jours(paires):
    """Moyenne en jours d'une liste de couples (date_debut, date_fin)."""
    ecarts = [
        (fin - debut).days
        for debut, fin in paires
        if debut is not None and fin is not None
    ]
    if not ecarts:
        return None
    return round(sum(ecarts) / len(ecarts), 1)


def _compter_par(queryset, champ_label):
    """Regroupe un queryset par un champ et retourne [{label, total}, ...]."""
    lignes = (
        queryset.values(label=F(champ_label))
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    return [
        {"label": ligne["label"] or "Non affecté", "total": ligne["total"]}
        for ligne in lignes
    ]


class StatistiquesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = _role(request.user)

        if role in ("dg", "secretaire", "admin"):
            return Response(self._statistiques_globales(role))

        if role == "chef_departement":
            if not request.user.departement_id:
                return Response(
                    {"detail": "Aucun département associé à votre compte."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(self._statistiques_departement(request.user))

        return Response(
            {"detail": "Les statistiques sont réservées au DG, au Secrétaire, à l'Admin et aux Chefs de Département."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # ------------------------------------------------------------------
    # DG / Admin — statistiques globales
    # ------------------------------------------------------------------

    def _statistiques_globales(self, role):
        courriers = Courrier.objects.all()
        entrants = courriers.filter(type_courrier="entrant")
        aujourd_hui = date.today()

        # Nombre de courriers par mois (12 derniers mois)
        par_mois = (
            courriers.annotate(mois=TruncMonth("date_creation"))
            .values("mois")
            .annotate(total=Count("id"))
            .order_by("-mois")[:12]
        )

        # Délai date source → réception
        delai_source_reception = _moyenne_jours(
            entrants.filter(
                date_source__isnull=False, date_reception__isnull=False
            ).values_list("date_source", "date_reception")
        )

        # Délai réception → affectation finale (via l'historique)
        affectations = Historique.objects.filter(
            action="affect_finale",
            courrier__date_reception__isnull=False,
        ).values_list("courrier__date_reception", "date")
        delai_reception_affectation = _moyenne_jours(
            [(reception, horodatage.date()) for reception, horodatage in affectations]
        )

        # Délai moyen de traitement (réception → clôture)
        clotures = Historique.objects.filter(
            action="cloture",
            courrier__date_reception__isnull=False,
        ).values_list("courrier__date_reception", "date")
        delai_traitement = _moyenne_jours(
            [(reception, horodatage.date()) for reception, horodatage in clotures]
        )

        donnees = {
            "role_rapport": "global",
            "totaux": {
                "courriers": courriers.count(),
                "entrants": entrants.count(),
                "sortants": courriers.filter(type_courrier="sortant").count(),
                "traites": courriers.filter(statut__in=("traite", "archive")).count(),
                "en_retard": courriers.filter(
                    date_echeance__lt=aujourd_hui
                ).exclude(statut__in=STATUTS_OUVERTS_EXCLUS).count(),
                "retournes_dg": Historique.objects.filter(action="retour_dg").count(),
            },
            "par_mois": [
                {
                    "mois": ligne["mois"].strftime("%Y-%m") if ligne["mois"] else "?",
                    "total": ligne["total"],
                }
                for ligne in par_mois
            ],
            "par_departement": _compter_par(entrants, "departement__nom"),
            "affectation_provisoire": {
                "avec": entrants.filter(affectations_provisoires__isnull=False).distinct().count(),
                "sans": entrants.filter(affectations_provisoires__isnull=True).count(),
            },
            "retours_par_departement": [
                {"label": ligne["label"] or "—", "total": ligne["total"]}
                for ligne in Historique.objects.filter(action="retour_dg")
                .values(label=F("auteur__departement__nom"))
                .annotate(total=Count("id"))
                .order_by("-total")
            ],
            "avec_instructions": courriers.filter(
                ~Q(instructions_dg="") | ~Q(instructions_chef_dept="")
            ).count(),
            "delais": {
                "source_vers_reception": delai_source_reception,
                "reception_vers_affectation": delai_reception_affectation,
                "traitement_moyen": delai_traitement,
            },
        }

        # Modifications par utilisateur : Admin uniquement
        if role == "admin":
            donnees["modifications_par_utilisateur"] = [
                {"label": ligne["label"], "total": ligne["total"]}
                for ligne in Historique.objects.filter(action="modification")
                .values(label=F("auteur__username"))
                .annotate(total=Count("id"))
                .order_by("-total")
            ]

        return donnees

    # ------------------------------------------------------------------
    # Chef de Département — statistiques de son département
    # ------------------------------------------------------------------

    def _statistiques_departement(self, utilisateur):
        courriers = Courrier.objects.filter(
            departement_id=utilisateur.departement_id
        )
        aujourd_hui = date.today()

        return {
            "role_rapport": "departement",
            "departement": str(utilisateur.departement),
            "totaux": {
                "courriers": courriers.count(),
                "en_cours": courriers.filter(statut="en_traitement").count(),
                "traites": courriers.filter(statut__in=("traite", "archive")).count(),
                "en_retard": courriers.filter(
                    date_echeance__lt=aujourd_hui
                ).exclude(statut__in=STATUTS_OUVERTS_EXCLUS).count(),
                "avec_instructions_dg": courriers.filter(
                    ~Q(instructions_dg="")
                ).count(),
            },
            "par_service": _compter_par(courriers, "service__nom"),
            "par_statut": [
                {"label": ligne["label"], "total": ligne["total"]}
                for ligne in courriers.values(label=F("statut"))
                .annotate(total=Count("id"))
                .order_by("-total")
            ],
        }
