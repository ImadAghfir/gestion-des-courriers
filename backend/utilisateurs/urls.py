from django.urls import path

from .views import MonProfilView

urlpatterns = [
    path("me/", MonProfilView.as_view(), name="mon-profil"),
]