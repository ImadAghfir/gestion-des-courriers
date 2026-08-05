from rest_framework import serializers
from .models import Courrier


class CourrierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Courrier
        fields = "__all__"
        read_only_fields = (
            "numero",
            "statut",
            "date_creation",
            "createur",
        )