from rest_framework.permissions import SAFE_METHODS, BasePermission


def est_administrateur(utilisateur):
    if not utilisateur or not utilisateur.is_authenticated:
        return False
    return utilisateur.is_superuser or getattr(utilisateur, "role", "") == "admin"


class LectureAuthentifieeEcritureAdmin(BasePermission):
    """
    Lecture : tout utilisateur connecté (listes déroulantes de l'application).
    Écriture : administrateur uniquement (cahier des charges §5.11 et §5.12).
    """

    message = "Seul l'administrateur peut effectuer cette opération."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return est_administrateur(request.user)
