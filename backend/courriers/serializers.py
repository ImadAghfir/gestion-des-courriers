from rest_framework import serializers

from historique.models import Historique
from .models import Courrier


class HistoriqueSerializer(serializers.ModelSerializer):
    auteur_nom = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = Historique
        fields = (
            "id", "action", "action_label", "auteur", "auteur_nom",
            "champ_modifie", "ancienne_valeur", "nouvelle_valeur",
            "commentaire", "date",
        )

    def get_auteur_nom(self, obj):
        return obj.auteur.get_full_name() or obj.auteur.username


class CourrierSerializer(serializers.ModelSerializer):
    """
    Sérialiseur avec visibilité par rôle (cahier des charges §10.3) :

    - affectation provisoire : DG, Admin et Bureau d'Ordre uniquement (AP-03) ;
    - instructions DG : DG, Admin et Chef de Département concerné (RI-01) ;
    - instructions Chef Dept : Chef Dept, Chef de Service, DG, Admin (RI-02) ;
    - historique complet : DG et Admin uniquement.
    """

    departement_nom = serializers.StringRelatedField(source="departement", read_only=True)
    service_nom = serializers.StringRelatedField(source="service", read_only=True)
    affectation_provisoire_nom = serializers.StringRelatedField(
        source="affectation_provisoire", read_only=True
    )
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    historique = HistoriqueSerializer(source="historiques", many=True, read_only=True)

    class Meta:
        model = Courrier
        fields = (
            "id", "numero", "numero_source", "type_courrier", "objet",
            "description", "expediteur", "destinataire", "categorie",
            "priorite", "statut", "statut_label",
            "date_reception", "date_source", "date_echeance", "date_creation",
            "fichier",
            "affectation_provisoire", "affectation_provisoire_nom",
            "departement", "departement_nom", "service", "service_nom",
            "instructions_dg", "instructions_chef_dept",
            "createur", "historique",
        )
        read_only_fields = (
            "numero", "statut", "date_creation", "createur",
            "departement", "service",
            "instructions_dg", "instructions_chef_dept",
        )

    def _role(self):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return ""
        if request.user.is_superuser:
            return "admin"
        return getattr(request.user, "role", "")

    def to_representation(self, instance):
        donnees = super().to_representation(instance)
        role = self._role()

        # AP-03 : affectation provisoire non visible par les Chefs
        if role not in ("admin", "dg", "secretaire", "bureau_ordre"):
            donnees.pop("affectation_provisoire", None)
            donnees.pop("affectation_provisoire_nom", None)

        # RI-01 : instructions DG → DG, Secrétaire, Admin, Chef de Département
        if role not in ("admin", "dg", "secretaire", "chef_departement"):
            donnees.pop("instructions_dg", None)

        # RI-02 : instructions Chef Dept → Chef Dept, Chef Service, DG, Secrétaire, Admin
        if role not in ("admin", "dg", "secretaire", "chef_departement", "chef_service"):
            donnees.pop("instructions_chef_dept", None)

        # Historique complet : DG, Secrétaire et Admin
        if role not in ("admin", "dg", "secretaire"):
            donnees.pop("historique", None)

        return donnees

    def validate(self, donnees):
        type_courrier = donnees.get("type_courrier") or getattr(
            self.instance, "type_courrier", None
        )

        if self.instance is None:
            if type_courrier == Courrier.TypeCourrier.ENTRANT:
                if not donnees.get("date_reception"):
                    raise serializers.ValidationError(
                        {"date_reception": "La date de réception est obligatoire pour un courrier entrant."}
                    )
                if not donnees.get("expediteur"):
                    raise serializers.ValidationError(
                        {"expediteur": "L'expéditeur est obligatoire pour un courrier entrant."}
                    )
            if type_courrier == Courrier.TypeCourrier.SORTANT:
                if not donnees.get("destinataire"):
                    raise serializers.ValidationError(
                        {"destinataire": "Le destinataire est obligatoire pour un courrier sortant."}
                    )
                if donnees.get("affectation_provisoire"):
                    raise serializers.ValidationError(
                        {"affectation_provisoire": "L'affectation provisoire ne concerne que les courriers entrants."}
                    )

        return donnees
