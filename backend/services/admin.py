from django.contrib import admin
from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "statut", "responsable")
    list_filter = ("statut",)
    search_fields = ("nom", "code")