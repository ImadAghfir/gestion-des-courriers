from rest_framework import permissions, viewsets

from .models import Courrier
from .serializers import CourrierSerializer


class CourrierViewSet(viewsets.ModelViewSet):
    queryset = Courrier.objects.all()
    serializer_class = CourrierSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)