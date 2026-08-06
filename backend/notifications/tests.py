from rest_framework.test import APITestCase

from courriers.models import Courrier
from .models import Notification
from services.models import Service
from utilisateurs.models import Utilisateur


class NotificationApiTest(APITestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Direction", code="DIR")
        self.user = Utilisateur.objects.create_user(
            username="agent", password="pass", service=self.service
        )
        self.other_user = Utilisateur.objects.create_user(
            username="autre", password="pass", service=self.service
        )
        self.courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Courrier de test",
            categorie="Administratif",
            createur=self.user,
            service=self.service,
        )
        self.notification = Notification.objects.create(
            destinataire=self.user,
            courrier=self.courrier,
            message="Un courrier vous a été affecté.",
        )
        self.other_notification = Notification.objects.create(
            destinataire=self.other_user,
            message="Notification privée.",
        )

    def test_liste_limitee_au_destinataire(self):
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.notification.id])
        self.assertEqual(response.data[0]["courrier_numero"], self.courrier.numero)

    def test_marquer_lue_ne_concerne_que_ses_notifications(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/notifications/{self.notification.id}/marquer_lue/"
        )

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.lu)

        response = self.client.post(
            f"/api/notifications/{self.other_notification.id}/marquer_lue/"
        )
        self.assertEqual(response.status_code, 404)
