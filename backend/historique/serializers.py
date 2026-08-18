from rest_framework import serializers

from .models import Historique


class JournalSerializer(serializers.ModelSerializer):
    """Entrée du journal d'activité global (cahier des charges §4.2)."""

    auteur_nom = serializers.SerializerMethodField()
    auteur_role = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)
    courrier_numero = serializers.CharField(
        source="courrier.numero", read_only=True, default=None
    )
    courrier_objet = serializers.CharField(
        source="courrier.objet", read_only=True, default=None
    )

    class Meta:
        model = Historique
        fields = (
            "id", "date",
            "auteur", "auteur_nom", "auteur_role",
            "action", "action_label",
            "courrier", "courrier_numero", "courrier_objet",
            "champ_modifie", "ancienne_valeur", "nouvelle_valeur",
            "commentaire",
        )

    def get_auteur_nom(self, obj):
        return obj.auteur.get_full_name() or obj.auteur.username

    def get_auteur_role(self, obj):
        return obj.auteur.get_role_display() or "—"
