from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from services.models import Departement, Service

from . import ai, services
from .models import Courrier
from .serializers import CourrierSerializer


def _reponse_erreur(exc):
    """Convertit une exception métier en réponse HTTP appropriée."""
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    message = getattr(exc, "message", None) or "; ".join(
        m for messages in getattr(exc, "message_dict", {}).values() for m in messages
    ) or str(exc)
    return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)


class CourrierViewSet(viewsets.ModelViewSet):
    """
    API des courriers — chaque acteur voit uniquement son périmètre
    (cahier des charges §5.3.4) :

    - Admin / DG : tous les courriers ;
    - Bureau d'Ordre : les courriers qu'il a enregistrés ;
    - Chef de Département : les courriers affectés à son département
      (après affectation finale) ;
    - Chef de Service : les courriers affectés à son service.
    """

    serializer_class = CourrierSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        utilisateur = self.request.user
        courriers = Courrier.objects.select_related(
            "departement", "service", "createur"
        ).prefetch_related("affectations_provisoires", "historiques__auteur")

        role = services._role(utilisateur)

        if role in ("admin", "dg", "secretaire"):
            perimetre = courriers
        elif role == "bureau_ordre":
            perimetre = courriers.filter(createur=utilisateur)
        elif role == "chef_departement":
            perimetre = courriers.filter(
                departement_id=utilisateur.departement_id,
                departement_id__isnull=False,
                statut__in=["affecte", "en_traitement", "traite", "archive"],
            )
        elif role == "chef_service":
            perimetre = courriers.filter(
                service_id=utilisateur.service_id,
                service_id__isnull=False,
                statut__in=["affecte", "en_traitement", "traite", "archive"],
            )
        else:
            perimetre = courriers.none()

        return self._appliquer_filtres(perimetre)

    def _appliquer_filtres(self, queryset):
        """
        Recherche avancée (cahier des charges §5.7).

        Paramètres de requête acceptés :
        - q : texte libre (n° interne, n° source, objet, expéditeur,
          destinataire, description) ;
        - statut, priorite, type_courrier, categorie : valeur exacte ;
        - departement, service : identifiant ;
        - reception_du / reception_au : période de réception ;
        - source_du / source_au : période de la date source ;
        - avec_instructions : "oui" ou "non".
        """
        params = self.request.query_params

        q = params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(numero__icontains=q)
                | Q(numero_source__icontains=q)
                | Q(objet__icontains=q)
                | Q(expediteur__icontains=q)
                | Q(destinataire__icontains=q)
                | Q(description__icontains=q)
            )

        for champ in ("statut", "priorite", "type_courrier", "categorie"):
            valeur = params.get(champ, "").strip()
            if valeur:
                queryset = queryset.filter(**{champ: valeur})

        for param, champ in (
            ("departement", "departement_id"),
            ("service", "service_id"),
        ):
            valeur = params.get(param, "").strip()
            if valeur.isdigit():
                queryset = queryset.filter(**{champ: int(valeur)})

        for param, champ in (
            ("reception_du", "date_reception__gte"),
            ("reception_au", "date_reception__lte"),
            ("source_du", "date_source__gte"),
            ("source_au", "date_source__lte"),
        ):
            valeur = params.get(param, "").strip()
            if valeur:
                try:
                    valeur = date.fromisoformat(valeur)
                except ValueError:
                    continue  # date invalide : filtre ignoré
                queryset = queryset.filter(**{champ: valeur})

        avec_instructions = params.get("avec_instructions", "").strip().lower()
        if avec_instructions == "oui":
            queryset = queryset.filter(
                ~Q(instructions_dg="") | ~Q(instructions_chef_dept="")
            )
        elif avec_instructions == "non":
            queryset = queryset.filter(
                instructions_dg="", instructions_chef_dept=""
            )

        return queryset

    # ------------------------------------------------------------------
    # Enregistrement (Bureau d'Ordre) — §5.3.2 / §5.3.3
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=["post"],
        url_path="analyser-document",
        parser_classes=[MultiPartParser, FormParser],
    )
    def analyser_document(self, request):
        """Analyse localement un document et renvoie des champs suggérés."""
        if services._role(request.user) not in ("admin", "bureau_ordre"):
            return Response(
                {"detail": "Vous n'avez pas l'autorisation d'analyser un courrier."},
                status=status.HTTP_403_FORBIDDEN,
            )

        fichier = request.FILES.get("fichier")
        if not fichier:
            return Response(
                {"detail": "Aucun fichier fourni (champ 'fichier' attendu)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if fichier.size > 10 * 1024 * 1024:
            return Response(
                {"detail": "Le document dépasse la taille maximale autorisée (10 Mo)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            suggestions = ai.analyser_document(fichier)
        except ai.AnalyseDocumentErreur as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({
            "suggestions": suggestions,
            "detail": "Suggestions générées localement. Vérifiez-les avant l'enregistrement.",
        })

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            courrier = services.enregistrer_courrier(
                request.user, serializer.validated_data
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)

        return Response(
            self.get_serializer(courrier).data, status=status.HTTP_201_CREATED
        )

    # ------------------------------------------------------------------
    # Modification contrôlée — §5.3.7
    # ------------------------------------------------------------------

    def partial_update(self, request, *args, **kwargs):
        courrier = self.get_object()
        serializer = self.get_serializer(
            courrier, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        commentaire = request.data.get("commentaire_modification", "")

        try:
            services.modifier_courrier(
                courrier, request.user, serializer.validated_data, commentaire
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)

        return Response(self.get_serializer(courrier).data)

    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": "Utilisez PATCH pour une modification contrôlée."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # ------------------------------------------------------------------
    # Workflow v3.3
    # ------------------------------------------------------------------

    def _action_simple(self, request, fonction, **kwargs):
        courrier = self.get_object()
        try:
            fonction(
                courrier,
                request.user,
                commentaire=request.data.get("commentaire", ""),
                **kwargs,
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"])
    def transmettre(self, request, pk=None):
        """Bureau d'Ordre → transmet le courrier au DG."""
        return self._action_simple(request, services.transmettre_au_dg)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """DG → valide le courrier."""
        return self._action_simple(request, services.valider_courrier)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        """DG → rejette le courrier (commentaire obligatoire)."""
        courrier = self.get_object()
        try:
            services.rejeter_courrier(
                courrier, request.user, request.data.get("commentaire", "")
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"], url_path="affectation-finale")
    def affectation_finale(self, request, pk=None):
        """
        DG → affectation finale officielle (ou réaffectation après retour).

        Corps JSON : { "departement_id": 1, "instructions": "...", "commentaire": "..." }
        """
        courrier = self.get_object()

        departement = None
        departement_id = request.data.get("departement_id")
        if departement_id:
            try:
                departement = Departement.objects.get(
                    pk=departement_id, statut=Departement.Statut.ACTIF
                )
            except Departement.DoesNotExist:
                return Response(
                    {"detail": "Département introuvable ou inactif."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            services.affectation_finale(
                courrier,
                request.user,
                departement,
                instructions=request.data.get("instructions", ""),
                commentaire=request.data.get("commentaire", ""),
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)

        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"], url_path="instructions-dg")
    def instructions_dg(self, request, pk=None):
        """DG → ajoute ou met à jour ses instructions."""
        courrier = self.get_object()
        try:
            services.donner_instructions_dg(
                courrier, request.user, request.data.get("instructions", "")
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"], url_path="retourner-dg")
    def retourner_dg(self, request, pk=None):
        """Chef de Département → retourne le courrier au DG (commentaire obligatoire)."""
        courrier = self.get_object()
        try:
            services.retourner_au_dg(
                courrier, request.user, request.data.get("commentaire", "")
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"], url_path="affecter-service")
    def affecter_service(self, request, pk=None):
        """
        Chef de Département → affecte le courrier à un service de son département.

        Corps JSON : { "service_id": 1, "instructions": "...", "commentaire": "..." }
        """
        courrier = self.get_object()

        service = None
        service_id = request.data.get("service_id")
        if service_id:
            try:
                service = Service.objects.get(
                    pk=service_id, statut=Service.Statut.ACTIF
                )
            except Service.DoesNotExist:
                return Response(
                    {"detail": "Service introuvable ou inactif."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            services.affecter_au_service(
                courrier,
                request.user,
                service,
                instructions=request.data.get("instructions", ""),
                commentaire=request.data.get("commentaire", ""),
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)

        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"], url_path="instructions-dept")
    def instructions_dept(self, request, pk=None):
        """Chef de Département → ajoute ou met à jour ses instructions."""
        courrier = self.get_object()
        try:
            services.donner_instructions_chef_dept(
                courrier, request.user, request.data.get("instructions", "")
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"])
    def traiter(self, request, pk=None):
        """Chef de Service → démarre le traitement."""
        return self._action_simple(request, services.traiter_courrier)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        """Chef de Service → clôture le traitement (statut TRAITÉ)."""
        return self._action_simple(request, services.cloturer_courrier)

    @action(detail=True, methods=["post"])
    def archiver(self, request, pk=None):
        """Bureau d'Ordre → archive définitivement le courrier."""
        return self._action_simple(request, services.archiver_courrier)

    @action(detail=True, methods=["post"])
    def envoyer(self, request, pk=None):
        """Bureau d'Ordre → marque un courrier sortant comme envoyé."""
        return self._action_simple(request, services.envoyer_courrier)

    # ------------------------------------------------------------------
    # Commentaires et documents
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"])
    def commenter(self, request, pk=None):
        """Ajoute un commentaire tracé dans l'historique."""
        courrier = self.get_object()
        try:
            services.ajouter_commentaire(
                courrier, request.user, request.data.get("commentaire", "")
            )
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)
        return Response({"detail": "Commentaire ajouté."})

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def ajouter_document(self, request, pk=None):
        """Attache un fichier au courrier (multipart, champ 'fichier')."""
        courrier = self.get_object()
        fichier = request.FILES.get("fichier")

        if not fichier:
            return Response(
                {"detail": "Aucun fichier fourni (champ 'fichier' attendu)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            services.ajouter_document(courrier, request.user, fichier)
        except (ValidationError, PermissionDenied) as exc:
            return _reponse_erreur(exc)

        return Response(self.get_serializer(courrier).data)

    # ------------------------------------------------------------------
    # Aides pour le frontend
    # ------------------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="statuts-suivants")
    def statuts_suivants(self, request, pk=None):
        """Statuts atteignables depuis l'état actuel."""
        courrier = self.get_object()
        return Response({"statuts": services.get_statuts_suivants(courrier)})
