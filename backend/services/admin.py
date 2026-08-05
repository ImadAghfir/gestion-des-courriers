from django.contrib import admin
from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "actif")
    list_filter = ("actif",)
    search_fields = ("nom", "code")