from django.urls import path

from .views import StatistiquesView

urlpatterns = [
    path("", StatistiquesView.as_view(), name="statistiques"),
]
