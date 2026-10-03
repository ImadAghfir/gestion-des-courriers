from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from services.views import DepartementViewSet, ServiceViewSet
from utilisateurs.views import (
    ChangerMotDePasseView,
    ConnexionView,
    MonProfilView,
    UtilisateurViewSet,
)

# Départements, services et utilisateurs : lecture par tous les utilisateurs
# connectés, création / modification / désactivation par l'administrateur
# (cahier des charges §5.11 et §5.12).
routeur_organisation = DefaultRouter()
routeur_organisation.register("departements", DepartementViewSet, basename="departement")
routeur_organisation.register("services", ServiceViewSet, basename="service")
routeur_organisation.register("utilisateurs", UtilisateurViewSet, basename="utilisateur")

urlpatterns = [
    # Django expose l'API ; l'application React est servie par Vite.
    # Cette redirection évite une page 404 lorsqu'on ouvre le port 8000.
    path("", RedirectView.as_view(url=settings.FRONTEND_URL, permanent=False)),
    path("admin/", admin.site.urls),
    path("api/", include("courriers.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include(routeur_organisation.urls)),
    path("api/statistiques/", include("statistiques.urls")),
    path("api/journal/", include("historique.urls")),
    path("api/auth/login/", ConnexionView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/me/", MonProfilView.as_view(), name="mon-profil"),
    path(
        "api/auth/changer-mot-de-passe/",
        ChangerMotDePasseView.as_view(),
        name="changer-mot-de-passe",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
