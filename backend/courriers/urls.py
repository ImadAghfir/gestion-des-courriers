from rest_framework.routers import DefaultRouter

from .views import CourrierViewSet

router = DefaultRouter()
router.register("courriers", CourrierViewSet, basename="courrier")

urlpatterns = router.urls