from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Informations supplémentaires", {"fields": ("role", "service")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Informations supplémentaires", {"fields": ("role", "service")}),
    )
    list_display = ("username", "email", "role", "service", "is_staff")
    list_filter = ("role", "service", "is_staff", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")