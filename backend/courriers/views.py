from django.core.exceptions import ValidationError
from django.db.models import Q

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from historique.models import Historique

from . import services
from .models import Courrier
from .serializers import CourrierSerializer


class CourrierViewSet(viewsets.ModelViewSet):
    serializer_class = CourrierSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        utilisateur = self.request.user
        courriers = Courrier.objects.select_related("service", "createur").all()

        if utilisateur.is_superuser:
            return courriers

        role = getattr(utilisateur, "role", "agent")
        if role in ("admin", "responsable"):
            return courriers

        # Un agent doit pouvoir suivre les courriers qu'il a créés ainsi que
        # ceux qui lui ont été affectés (directement ou à son service).
        conditions = Q(createur=utilisateur) | Q(affectations__utilisateur=utilisateur)
        if utilisateur.service_id:
            conditions |= Q(affectations__service_id=utilisateur.service_id)

        return courriers.filter(conditions).distinct()

    def _est_responsable_ou_admin(self, utilisateur):
        if utilisateur.is_superuser:
            return True
        return getattr(utilisateur, "role", "agent") in ("admin", "responsable")

    # ------------------------------------------------------------------
    # Création
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        courrier = serializer.save(createur=self.request.user)

        Historique.objects.create(
            courrier=courrier,
            auteur=self.request.user,
            action=Historique.Action.CREATION,
            commentaire="Création du courrier.",
        )

        # Alerte immédiate si priorité élevée
        services.notifier_responsable_si_urgent(courrier, declencheur=self.request.user)

    # ------------------------------------------------------------------
    # Action générique : changement de statut (via la machine à états)
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="changer-statut")
    def changer_statut(self, request, pk=None):
        """
        Change le statut d'un courrier en respectant la machine à états.

        Corps JSON attendu :
            { "statut": "en_cours", "commentaire": "..." }
        """
        courrier = self.get_object()
        nouveau_statut = request.data.get("statut")
        commentaire = request.data.get("commentaire", "")

        if not nouveau_statut:
            return Response(
                {"detail": "Le champ 'statut' est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            services.changer_statut(courrier, nouveau_statut, request.user, commentaire)
        except ValidationError as exc:
            return Response(
                {"detail": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(self.get_serializer(courrier).data)

    # ------------------------------------------------------------------
    # Action : soumettre un courrier sortant à la validation
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"])
    def soumettre_validation(self, request, pk=None):
        """BROUILLON → EN_VALIDATION (courrier sortant uniquement)."""
        courrier = self.get_object()

        if courrier.type_courrier != Courrier.TypeCourrier.SORTANT:
            return Response(
                {"detail": "Seuls les courriers sortants peuvent être soumis à validation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            services.changer_statut(
                courrier, "en_validation", request.user,
                "Courrier soumis pour validation."
            )
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(courrier).data)

    # ------------------------------------------------------------------
    # Action : valider un courrier sortant
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """EN_VALIDATION → VALIDE. Réservé aux responsables et admins."""
        courrier = self.get_object()

        if not self._est_responsable_ou_admin(request.user):
            return Response(
                {"detail": "Seul un responsable ou administrateur peut valider un courrier."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if courrier.type_courrier != Courrier.TypeCourrier.SORTANT:
            return Response(
                {"detail": "Seuls les courriers sortants peuvent être validés."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            services.valider_courrier(courrier, request.user)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(courrier).data)

    # ------------------------------------------------------------------
    # Action : affecter un courrier
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"])
    def affecter(self, request, pk=None):
        """
        Affecte le courrier à un utilisateur et/ou un service.

        Corps JSON attendu :
            {
                "utilisateur_id": 3,       # optionnel
                "service_id": 1,           # optionnel (au moins un des deux)
                "commentaire": "..."       # optionnel
            }
        """
        from django.contrib.auth import get_user_model
        from services.models import Service

        if not self._est_responsable_ou_admin(request.user):
            return Response(
                {"detail": "Seul un responsable ou administrateur peut affecter un courrier."},
                status=status.HTTP_403_FORBIDDEN,
            )

        courrier = self.get_object()
        User = get_user_model()

        utilisateur_id = request.data.get("utilisateur_id")
        service_id = request.data.get("service_id")
        commentaire = request.data.get("commentaire", "")

        utilisateur_cible = None
        service_cible = None

        if utilisateur_id:
            try:
                utilisateur_cible = User.objects.get(pk=utilisateur_id, is_active=True)
            except User.DoesNotExist:
                return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if service_id:
            try:
                service_cible = Service.objects.get(
                    pk=service_id,
                    statut=Service.Statut.ACTIF,
                )
            except Service.DoesNotExist:
                return Response({"detail": "Service introuvable."}, status=status.HTTP_404_NOT_FOUND)

        try:
            services.affecter_courrier(
                courrier, request.user,
                utilisateur_cible=utilisateur_cible,
                service_cible=service_cible,
                commentaire=commentaire,
            )
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(courrier).data)

    # ------------------------------------------------------------------
    # Action : ajouter un commentaire
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"])
    def commenter(self, request, pk=None):
        """
        Ajoute un commentaire tracé dans Historique.

        Corps JSON attendu : { "commentaire": "..." }
        """
        courrier = self.get_object()
        commentaire = request.data.get("commentaire", "")

        try:
            services.ajouter_commentaire(courrier, request.user, commentaire)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Commentaire ajouté."})

    # ------------------------------------------------------------------
    # Action : attacher un document
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def ajouter_document(self, request, pk=None):
        """
        Attache un fichier au courrier et trace l'ajout dans Historique.

        Envoi multipart/form-data avec le champ 'fichier'.
        """
        courrier = self.get_object()
        fichier = request.FILES.get("fichier")

        if not fichier:
            return Response(
                {"detail": "Aucun fichier fourni (champ 'fichier' attendu)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            services.ajouter_document(courrier, request.user, fichier)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(courrier).data)

    # ------------------------------------------------------------------
    # Action : statuts atteignables (aide pour le frontend)
    # ------------------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="statuts-suivants")
    def statuts_suivants(self, request, pk=None):
        """
        Retourne la liste des statuts autorisés depuis l'état actuel.
        Permet au frontend d'afficher uniquement les actions disponibles.
        """
        courrier = self.get_object()
        return Response({"statuts": services.get_statuts_suivants(courrier)})
