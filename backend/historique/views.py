"""
Journal d'activité global — cahier des charges §4.2.

« L'Administrateur peut accéder aux journaux d'activité. »

Cette vue expose l'ensemble des actions tracées sur tous les courriers de
l'organisation, avec filtres et pagination. L'accès est réservé à
l'administrateur : les autres acteurs consultent l'historique courrier par
courrier, dans leur propre périmètre (§10.3).
"""
from datetime import date

from django.db.models import Q

from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Historique
from .serializers import JournalSerializer


class EstAdministrateur(BasePermission):
    message = "Le journal d'activité est réservé à l'administrateur."

    def has_permission(self, request, view):
        utilisateur = request.user
        if not utilisateur.is_authenticated:
            return False
        return utilisateur.is_superuser or getattr(utilisateur, "role", "") == "admin"


class PaginationJournal(PageNumberPagination):
    page_size = 50
    page_size_query_param = "taille"
    max_page_size = 200


class JournalActiviteView(ListAPIView):
    """
    Journal filtrable.

    Paramètres acceptés :
    - q : recherche libre (numéro de courrier, objet, commentaire, utilisateur) ;
    - action : type d'action exact ;
    - utilisateur : identifiant de l'auteur ;
    - courrier : identifiant du courrier ;
    - du / au : période (dates incluses) ;
    - page, taille : pagination.
    """

    serializer_class = JournalSerializer
    permission_classes = [EstAdministrateur]
    pagination_class = PaginationJournal

    def get_queryset(self):
        journal = Historique.objects.select_related(
            "auteur", "courrier"
        ).order_by("-date")

        params = self.request.query_params

        q = params.get("q", "").strip()
        if q:
            journal = journal.filter(
                Q(courrier__numero__icontains=q)
                | Q(courrier__objet__icontains=q)
                | Q(commentaire__icontains=q)
                | Q(auteur__username__icontains=q)
                | Q(auteur__first_name__icontains=q)
                | Q(auteur__last_name__icontains=q)
            )

        action = params.get("action", "").strip()
        if action:
            journal = journal.filter(action=action)

        for param, champ in (("utilisateur", "auteur_id"), ("courrier", "courrier_id")):
            valeur = params.get(param, "").strip()
            if valeur.isdigit():
                journal = journal.filter(**{champ: int(valeur)})

        for param, champ in (("du", "date__date__gte"), ("au", "date__date__lte")):
            valeur = params.get(param, "").strip()
            if valeur:
                try:
                    journal = journal.filter(**{champ: date.fromisoformat(valeur)})
                except ValueError:
                    continue  # date invalide : filtre ignoré

        return journal


class ActionsJournalView(APIView):
    """Liste des types d'action, pour alimenter le filtre du frontend."""

    permission_classes = [EstAdministrateur]

    def get(self, request):
        return Response(
            [
                {"valeur": valeur, "libelle": libelle}
                for valeur, libelle in Historique.Action.choices
            ]
        )
