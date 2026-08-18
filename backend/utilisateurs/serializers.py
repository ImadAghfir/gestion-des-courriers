from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from .models import Utilisateur


class UtilisateurSerializer(serializers.ModelSerializer):
    """Lecture simple (listes déroulantes, journal d'activité)."""

    class Meta:
        model = Utilisateur
        fields = (
            "id", "username", "first_name", "last_name",
            "role", "departement", "service",
        )


class UtilisateurAdminSerializer(serializers.ModelSerializer):
    """
    Gestion des comptes par l'administrateur (cahier des charges §5.11).

    Champs : nom, prénom, identifiant, e-mail, mot de passe, rôle,
    département, service, statut actif/inactif.
    """

    mot_de_passe = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )
    nom_complet = serializers.SerializerMethodField()
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    departement_nom = serializers.StringRelatedField(
        source="departement", read_only=True
    )
    service_nom = serializers.StringRelatedField(source="service", read_only=True)

    class Meta:
        model = Utilisateur
        fields = (
            "id", "username", "first_name", "last_name", "email",
            "role", "role_label", "departement", "departement_nom",
            "service", "service_nom", "is_active", "nom_complet",
            "doit_changer_mot_de_passe", "mot_de_passe",
        )
        read_only_fields = ("doit_changer_mot_de_passe",)

    def get_nom_complet(self, obj):
        return obj.get_full_name() or obj.username

    def validate_mot_de_passe(self, valeur):
        if not valeur:
            return valeur
        try:
            validate_password(valeur)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(" ".join(exc.messages))
        return valeur

    def validate(self, donnees):
        role = donnees.get("role") or getattr(self.instance, "role", "")
        departement = donnees.get(
            "departement", getattr(self.instance, "departement", None)
        )
        service = donnees.get("service", getattr(self.instance, "service", None))

        if not role:
            raise serializers.ValidationError(
                {"role": "Le rôle est obligatoire."}
            )

        # Cohérence entre le rôle et le rattachement (§4)
        if role == "chef_departement" and not departement:
            raise serializers.ValidationError(
                {"departement": "Un Chef de Département doit être rattaché à un département."}
            )
        if role == "chef_service" and not service:
            raise serializers.ValidationError(
                {"service": "Un Chef de Service doit être rattaché à un service."}
            )
        if service and departement and service.departement_id != departement.id:
            raise serializers.ValidationError(
                {"service": "Le service choisi n'appartient pas au département indiqué."}
            )
        if service and not departement:
            # Rattachement automatique au département du service
            donnees["departement"] = service.departement

        return donnees

    def create(self, donnees_validees):
        mot_de_passe = donnees_validees.pop("mot_de_passe", "") or None
        if not mot_de_passe:
            raise serializers.ValidationError(
                {"mot_de_passe": "Un mot de passe initial est obligatoire à la création."}
            )

        utilisateur = Utilisateur(**donnees_validees)
        utilisateur.set_password(mot_de_passe)
        # Changement imposé à la première connexion (§10.1)
        utilisateur.doit_changer_mot_de_passe = True
        utilisateur.save()
        return utilisateur

    def update(self, instance, donnees_validees):
        mot_de_passe = donnees_validees.pop("mot_de_passe", "") or None

        for champ, valeur in donnees_validees.items():
            setattr(instance, champ, valeur)

        if mot_de_passe:
            instance.set_password(mot_de_passe)
            instance.doit_changer_mot_de_passe = True
            # Un mot de passe réinitialisé débloque le compte
            instance.tentatives_echouees = 0
            instance.verrouille_jusqua = None

        instance.save()
        return instance
