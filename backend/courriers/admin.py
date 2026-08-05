from django.contrib import admin
from .models import Courrier


@admin.register(Courrier)
class CourrierAdmin(admin.ModelAdmin):
    list_display = (
        "numero", "type_courrier", "objet", "priorite",
        "statut", "service", "cree_par", "date_creation",
    )
    list_filter = ("type_courrier", "priorite", "statut", "service")
    search_fields = ("numero", "objet", "expediteur", "destinataire")
    readonly_fields = ("numero", "date_creation")