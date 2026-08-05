from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class MonProfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            role = "admin"
        else:
            role = getattr(request.user, "role", "agent")

        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "role": role,
            }
        )