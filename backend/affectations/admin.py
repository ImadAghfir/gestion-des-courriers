from django.contrib import admin
from .models import Affectation


@admin.register(Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display = ("courrier", "utilisateur", "service", "affecte_par", "date")
    list_filter = ("service",)
    search_fields = ("courrier__numero", "utilisateur__username")