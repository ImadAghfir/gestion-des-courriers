from django.urls import path

from .views import ListeUtilisateursView

urlpatterns = [
    path("", ListeUtilisateursView.as_view(), name="liste-utilisateurs"),
]