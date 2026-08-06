from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from utilisateurs.views import MonProfilView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("courriers.urls")),
    path("api/", include("notifications.urls")),
    path("api/services/", include("services.urls")),
    path("api/utilisateurs/", include("utilisateurs.urls")),
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/me/", MonProfilView.as_view(), name="mon-profil"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
