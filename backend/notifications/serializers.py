from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    courrier_numero = serializers.CharField(
        source="courrier.numero",
        read_only=True,
        default=None,
    )

    class Meta:
        model = Notification
        fields = (
            "id",
            "courrier",
            "courrier_numero",
            "message",
            "type",
            "lu",
            "date",
        )