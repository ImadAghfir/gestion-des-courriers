from django.contrib import admin

from .models import Departement, Service


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "statut", "responsable")
    list_filter = ("statut",)
    search_fields = ("nom", "code")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "departement", "statut", "responsable")
    list_filter = ("statut", "departement")
    search_fields = ("nom", "code")
