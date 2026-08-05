from django.contrib import admin
from .models import Historique


@admin.register(Historique)
class HistoriqueAdmin(admin.ModelAdmin):
    list_display = ("courrier", "action", "auteur", "date")
    list_filter = ("action",)
    search_fields = ("courrier__numero", "auteur__username")
    readonly_fields = ("date",)