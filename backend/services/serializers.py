from rest_framework import serializers

from .models import Departement, Service


class DepartementSerializer(serializers.ModelSerializer):
    responsable_nom = serializers.SerializerMethodField()
    nombre_services = serializers.SerializerMethodField()

    class Meta:
        model = Departement
        fields = (
            "id", "nom", "code", "description", "statut",
            "responsable", "responsable_nom", "nombre_services",
        )

    def get_responsable_nom(self, obj):
        if not obj.responsable:
            return None
        return obj.responsable.get_full_name() or obj.responsable.username

    def get_nombre_services(self, obj):
        return obj.services.count()

    def validate_code(self, valeur):
        return valeur.strip().upper()


class ServiceSerializer(serializers.ModelSerializer):
    # Un service appartient obligatoirement à un département (§5.12),
    # même si la colonne accepte NULL pour les données historiques.
    departement = serializers.PrimaryKeyRelatedField(
        queryset=Departement.objects.all(),
        required=True,
        allow_null=False,
        error_messages={"null": "Un service doit être rattaché à un département."},
    )
    departement_nom = serializers.StringRelatedField(
        source="departement", read_only=True
    )
    responsable_nom = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "id", "nom", "code", "description", "departement", "departement_nom",
            "statut", "responsable", "responsable_nom",
        )

    def get_responsable_nom(self, obj):
        if not obj.responsable:
            return None
        return obj.responsable.get_full_name() or obj.responsable.username

    def validate_code(self, valeur):
        return valeur.strip().upper()
