from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Utilisateur
from .permissions import LectureAuthentifieeEcritureAdmin, est_administrateur
from .serializers import UtilisateurAdminSerializer


class ConnexionView(TokenObtainPairView):
    """
    Connexion JWT avec blocage après 5 tentatives échouées (§10.1).

    - Compte verrouillé → 403 avec le temps d'attente restant.
    - Échec → compteur incrémenté ; au 5ᵉ échec, blocage 15 minutes.
    - Succès → compteur remis à zéro.
    """

    def post(self, request, *args, **kwargs):
        username = str(request.data.get("username", "")).strip()
        utilisateur = Utilisateur.objects.filter(username=username).first()

        if utilisateur and utilisateur.est_verrouille:
            return Response(
                {
                    "detail": (
                        "Compte temporairement bloqué après "
                        f"{Utilisateur.MAX_TENTATIVES} tentatives échouées. "
                        "Réessayez plus tard ou contactez l'administrateur."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            if utilisateur and utilisateur.is_active:
                utilisateur.enregistrer_echec_connexion()
                if utilisateur.est_verrouille:
                    return Response(
                        {
                            "detail": (
                                "Compte bloqué pour "
                                f"{Utilisateur.DUREE_VERROUILLAGE_MINUTES} minutes "
                                f"après {Utilisateur.MAX_TENTATIVES} tentatives échouées."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            return Response(
                {"detail": "Nom d'utilisateur ou mot de passe incorrect."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if utilisateur:
            utilisateur.reinitialiser_echecs_connexion()

        return response


class ChangerMotDePasseView(APIView):
    """Changement de mot de passe (obligatoire à la première connexion, §10.1)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ancien = request.data.get("ancien_mot_de_passe", "")
        nouveau = request.data.get("nouveau_mot_de_passe", "")

        if not request.user.check_password(ancien):
            return Response(
                {"detail": "L'ancien mot de passe est incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if ancien == nouveau:
            return Response(
                {"detail": "Le nouveau mot de passe doit être différent de l'ancien."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(nouveau, request.user)
        except ValidationError as exc:
            return Response(
                {"detail": " ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(nouveau)
        request.user.doit_changer_mot_de_passe = False
        request.user.save(update_fields=["password", "doit_changer_mot_de_passe"])

        return Response({"detail": "Mot de passe modifié avec succès."})


class MonProfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        utilisateur = request.user
        role = "admin" if utilisateur.is_superuser else utilisateur.role

        return Response(
            {
                "id": utilisateur.id,
                "username": utilisateur.username,
                "nom_complet": utilisateur.get_full_name() or utilisateur.username,
                "role": role,
                "departement": utilisateur.departement_id,
                "departement_nom": (
                    str(utilisateur.departement) if utilisateur.departement else None
                ),
                "service": utilisateur.service_id,
                "service_nom": str(utilisateur.service) if utilisateur.service else None,
                "doit_changer_mot_de_passe": utilisateur.doit_changer_mot_de_passe,
            }
        )


class UtilisateurViewSet(viewsets.ModelViewSet):
    """
    Gestion des comptes utilisateurs — cahier des charges §5.11.

    - Lecture : tout utilisateur connecté (listes déroulantes) ;
    - Création / modification / activation : administrateur uniquement ;
    - Pas de suppression : les comptes sont désactivés, jamais effacés.
    """

    serializer_class = UtilisateurAdminSerializer
    permission_classes = [LectureAuthentifieeEcritureAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        utilisateurs = Utilisateur.objects.select_related(
            "departement", "service"
        ).order_by("username")

        # Les non-administrateurs ne voient que les comptes actifs
        if not est_administrateur(self.request.user):
            return utilisateurs.filter(is_active=True)

        # L'administrateur doit pouvoir agir sur un compte désactivé
        # (le réactiver, corriger ses informations) : le filtre ne
        # s'applique donc qu'à la liste.
        if self.action == "list" and self.request.query_params.get("tous") != "1":
            return utilisateurs.filter(is_active=True)

        return utilisateurs

    @action(detail=True, methods=["post"], url_path="changer-statut")
    def changer_statut(self, request, pk=None):
        """Active ou désactive un compte (sans suppression des données)."""
        utilisateur = self.get_object()

        if utilisateur.pk == request.user.pk:
            return Response(
                {"detail": "Vous ne pouvez pas désactiver votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        utilisateur.is_active = not utilisateur.is_active
        utilisateur.save(update_fields=["is_active"])

        return Response(self.get_serializer(utilisateur).data)

    @action(detail=True, methods=["post"], url_path="debloquer")
    def debloquer(self, request, pk=None):
        """Lève le blocage après 5 tentatives de connexion échouées (§10.1)."""
        utilisateur = self.get_object()
        utilisateur.reinitialiser_echecs_connexion()
        return Response(self.get_serializer(utilisateur).data)
