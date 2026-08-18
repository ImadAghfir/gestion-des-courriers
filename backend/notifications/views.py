import logging

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ControleEcheances, Notification
from .serializers import NotificationSerializer
from .services import verifier_echeances

journal = logging.getLogger(__name__)

#: Nombre de notifications renvoyées par défaut (les plus récentes).
#: Le compteur de non-lues reste exact grâce à l'action `compteur`.
LIMITE_PAR_DEFAUT = 50
LIMITE_MAXIMALE = 200


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            destinataire=self.request.user
        ).select_related("courrier")

    def list(self, request, *args, **kwargs):
        # Contrôle automatique des échéances (§5.9) : au plus une fois par
        # heure, déclenché par la consultation des notifications.
        # Une erreur de ce contrôle ne doit jamais empêcher l'utilisateur
        # de consulter ses notifications.
        if ControleEcheances.doit_executer(intervalle_minutes=60):
            try:
                verifier_echeances()
            except Exception:  # noqa: BLE001 - robustesse volontaire
                journal.exception(
                    "Échec du contrôle automatique des échéances ; "
                    "la liste des notifications reste accessible."
                )

        try:
            limite = int(request.query_params.get("limite", LIMITE_PAR_DEFAUT))
        except ValueError:
            limite = LIMITE_PAR_DEFAUT
        limite = max(1, min(limite, LIMITE_MAXIMALE))

        notifications = self.filter_queryset(self.get_queryset())[:limite]
        return Response(self.get_serializer(notifications, many=True).data)

    @action(detail=False, methods=["get"])
    def compteur(self, request):
        """Nombre de notifications non lues (indépendant de la pagination)."""
        return Response(
            {
                "non_lues": self.get_queryset().filter(lu=False).count(),
                "total": self.get_queryset().count(),
            }
        )

    @action(detail=True, methods=["post"])
    def marquer_lue(self, request, pk=None):
        notification = self.get_object()
        notification.lu = True
        notification.save(update_fields=["lu"])

        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="tout-marquer-lues")
    def tout_marquer_lues(self, request):
        """Marque toutes les notifications de l'utilisateur comme lues."""
        modifiees = self.get_queryset().filter(lu=False).update(lu=True)
        return Response({"detail": f"{modifiees} notification(s) marquée(s) comme lue(s)."})
