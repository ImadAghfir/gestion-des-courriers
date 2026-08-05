from django.contrib import admin
from .models import ProfilUtilisateur


@admin.register(ProfilUtilisateur)
class ProfilUtilisateurAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "role", "service", "actif")
    list_filter = ("role", "actif", "service")
    search_fields = ("utilisateur__username", "utilisateur__email")