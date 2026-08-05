from rest_framework import permissions, viewsets

from .models import Courrier
from .serializers import CourrierSerializer


class CourrierViewSet(viewsets.ModelViewSet):
    serializer_class = CourrierSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        utilisateur = self.request.user
        courriers = Courrier.objects.all()

        # Administrateur Django : accès total
        if utilisateur.is_superuser:
            return courriers

        profil = getattr(utilisateur, "profil", None)

        # Responsable et administrateur applicatif : accès total
        if profil and profil.role in ("admin", "responsable"):
            return courriers

        # Agent : seulement les courriers qu'il a créés
        return courriers.filter(cree_par=utilisateur)

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)