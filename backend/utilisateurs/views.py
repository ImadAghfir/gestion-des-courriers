from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Utilisateur
from .serializers import UtilisateurSerializer


class MonProfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = "admin" if request.user.is_superuser else request.user.role

        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "role": role,
            }
        )


class ListeUtilisateursView(ListAPIView):
    serializer_class = UtilisateurSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Utilisateur.objects.filter(is_active=True).order_by("username")