from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "courrier", "type", "lu", "date")
    list_filter = ("type", "lu")
    search_fields = ("utilisateur__username", "message")
    readonly_fields = ("date",)