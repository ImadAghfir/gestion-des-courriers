from django.contrib import admin
from .models import Courrier


@admin.register(Courrier)
class CourrierAdmin(admin.ModelAdmin):
    list_display = (
        "numero", "numero_source", "type_courrier", "objet", "priorite",
        "statut", "departement", "service", "createur", "date_creation",
    )
    list_filter = ("type_courrier", "priorite", "statut", "departement", "service")
    search_fields = ("numero", "numero_source", "objet", "expediteur", "destinataire")
    readonly_fields = ("numero", "date_creation")