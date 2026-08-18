"""
Gestion des départements et des services — cahier des charges §5.12.

Créer, modifier et désactiver (jamais supprimer : les données sont conservées).
Lecture ouverte à tous les utilisateurs connectés pour les listes déroulantes,
écriture réservée à l'administrateur.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from utilisateurs.permissions import LectureAuthentifieeEcritureAdmin, est_administrateur

from .models import Departement, Service
from .serializers import DepartementSerializer, ServiceSerializer


class BaseOrganisationViewSet(viewsets.ModelViewSet):
    permission_classes = [LectureAuthentifieeEcritureAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _inclure_inactifs(self):
        """
        L'administrateur voit les entités inactives sur demande (`?tous=1`)
        et toujours sur les vues de détail, afin de pouvoir les réactiver.
        """
        if not est_administrateur(self.request.user):
            return False
        if self.action != "list":
            return True
        return self.request.query_params.get("tous") == "1"

    @action(detail=True, methods=["post"], url_path="changer-statut")
    def changer_statut(self, request, pk=None):
        """Active ou désactive l'entité, sans suppression des données."""
        objet = self.get_object()
        objet.statut = "inactif" if objet.statut == "actif" else "actif"
        objet.save(update_fields=["statut"])
        return Response(self.get_serializer(objet).data)


class DepartementViewSet(BaseOrganisationViewSet):
    serializer_class = DepartementSerializer

    def get_queryset(self):
        departements = Departement.objects.order_by("nom")
        if self._inclure_inactifs():
            return departements
        return departements.filter(statut="actif")

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "La suppression n'est pas autorisée : désactivez le département."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class ServiceViewSet(BaseOrganisationViewSet):
    serializer_class = ServiceSerializer

    def get_queryset(self):
        services = Service.objects.select_related("departement").order_by("nom")

        if not self._inclure_inactifs():
            services = services.filter(statut="actif")

        departement = self.request.query_params.get("departement", "").strip()
        if departement.isdigit():
            services = services.filter(departement_id=int(departement))

        return services

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "La suppression n'est pas autorisée : désactivez le service."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )
