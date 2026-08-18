from django.urls import path

from .views import ActionsJournalView, JournalActiviteView

urlpatterns = [
    path("", JournalActiviteView.as_view(), name="journal-activite"),
    path("actions/", ActionsJournalView.as_view(), name="journal-actions"),
]
