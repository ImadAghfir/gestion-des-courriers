from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "courrier", "type", "lu", "date")
    list_filter = ("type", "lu")
    search_fields = ("destinataire__username", "message")
    readonly_fields = ("date",)