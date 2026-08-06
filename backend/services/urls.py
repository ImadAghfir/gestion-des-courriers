from django.urls import path

from .views import ListeServicesView

urlpatterns = [
    path("", ListeServicesView.as_view(), name="liste-services"),
]