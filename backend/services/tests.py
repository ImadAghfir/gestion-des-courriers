"""Gestion des départements et des services (cahier des charges §5.12)."""
from rest_framework.test import APITestCase

from utilisateurs.models import Utilisateur

from .models import Departement, Service


class GestionOrganisationTest(APITestCase):
    def setUp(self):
        self.dept = Departement.objects.create(nom="Ressources Humaines", code="RH")
        self.service = Service.objects.create(
            nom="Recrutement", code="RH1", departement=self.dept
        )

        self.admin = Utilisateur.objects.create_user(
            username="admin", password="pass", role="admin"
        )
        self.bo = Utilisateur.objects.create_user(
            username="bureau", password="pass", role="bureau_ordre"
        )

    # ---- Lecture ----------------------------------------------------

    def test_lecture_ouverte_aux_utilisateurs_connectes(self):
        self.client.force_authenticate(self.bo)

        self.assertEqual(self.client.get("/api/departements/").status_code, 200)
        self.assertEqual(self.client.get("/api/services/").status_code, 200)

    def test_lecture_refusee_sans_authentification(self):
        self.assertEqual(self.client.get("/api/departements/").status_code, 401)

    def test_filtre_services_par_departement(self):
        autre = Departement.objects.create(nom="Finances", code="FIN")
        Service.objects.create(nom="Comptabilité", code="FIN1", departement=autre)

        self.client.force_authenticate(self.bo)
        response = self.client.get("/api/services/", {"departement": self.dept.id})

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["code"], "RH1")

    # ---- Création et modification ------------------------------------

    def test_creation_departement_par_admin(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/departements/",
            {"nom": "Technique", "code": "tech"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        # Le code est normalisé en majuscules
        self.assertEqual(response.data["code"], "TECH")

    def test_creation_refusee_aux_non_admins(self):
        self.client.force_authenticate(self.bo)

        response = self.client.post(
            "/api/departements/", {"nom": "Pirate", "code": "PIR"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            "/api/services/",
            {"nom": "Pirate", "code": "PIR1", "departement": self.dept.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_modification_departement(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/departements/{self.dept.id}/",
            {"nom": "Ressources Humaines et Formation", "responsable": self.bo.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.dept.refresh_from_db()
        self.assertEqual(self.dept.nom, "Ressources Humaines et Formation")
        self.assertEqual(self.dept.responsable, self.bo)

    def test_service_sans_departement_refuse(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/services/", {"nom": "Orphelin", "code": "ORP"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    # ---- Désactivation (sans suppression) ----------------------------

    def test_desactivation_et_reactivation_departement(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(f"/api/departements/{self.dept.id}/changer-statut/")
        self.assertEqual(response.status_code, 200)
        self.dept.refresh_from_db()
        self.assertEqual(self.dept.statut, "inactif")

        # Absent de la liste par défaut, visible avec ?tous=1
        self.assertEqual(len(self.client.get("/api/departements/").data), 0)
        self.assertEqual(len(self.client.get("/api/departements/?tous=1").data), 1)

        # Réactivation possible
        response = self.client.post(f"/api/departements/{self.dept.id}/changer-statut/")
        self.assertEqual(response.status_code, 200)
        self.dept.refresh_from_db()
        self.assertEqual(self.dept.statut, "actif")

    def test_desactivation_service(self):
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/services/{self.service.id}/changer-statut/")

        self.service.refresh_from_db()
        self.assertEqual(self.service.statut, "inactif")
        # Les données sont conservées
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())

    def test_suppression_interdite(self):
        self.client.force_authenticate(self.admin)

        self.assertEqual(
            self.client.delete(f"/api/departements/{self.dept.id}/").status_code, 405
        )
        self.assertEqual(
            self.client.delete(f"/api/services/{self.service.id}/").status_code, 405
        )
