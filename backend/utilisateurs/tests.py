"""Tests de sécurité — cahier des charges §10.1."""
from django.utils import timezone

from rest_framework.test import APITestCase

from .models import Utilisateur


class BlocageConnexionTest(APITestCase):
    """Blocage après 5 tentatives de connexion échouées."""

    def setUp(self):
        self.utilisateur = Utilisateur.objects.create_user(
            username="bureau", password="BonMotDePasse_2026", role="bureau_ordre"
        )

    def _tenter(self, mot_de_passe):
        return self.client.post(
            "/api/auth/login/",
            {"username": "bureau", "password": mot_de_passe},
            format="json",
        )

    def test_blocage_apres_cinq_echecs(self):
        for numero in range(4):
            response = self._tenter("mauvais")
            self.assertEqual(response.status_code, 401, f"tentative {numero + 1}")

        # 5ᵉ échec → blocage annoncé
        response = self._tenter("mauvais")
        self.assertEqual(response.status_code, 403)
        self.assertIn("bloqué", response.data["detail"])

        # Même le bon mot de passe est refusé pendant le blocage
        response = self._tenter("BonMotDePasse_2026")
        self.assertEqual(response.status_code, 403)

        self.utilisateur.refresh_from_db()
        self.assertTrue(self.utilisateur.est_verrouille)

    def test_compteur_remis_a_zero_apres_succes(self):
        for _ in range(3):
            self._tenter("mauvais")

        response = self._tenter("BonMotDePasse_2026")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

        self.utilisateur.refresh_from_db()
        self.assertEqual(self.utilisateur.tentatives_echouees, 0)

    def test_deblocage_apres_expiration(self):
        self.utilisateur.verrouille_jusqua = timezone.now() - timezone.timedelta(minutes=1)
        self.utilisateur.save()

        response = self._tenter("BonMotDePasse_2026")
        self.assertEqual(response.status_code, 200)

        self.utilisateur.refresh_from_db()
        self.assertIsNone(self.utilisateur.verrouille_jusqua)


class ChangementMotDePasseTest(APITestCase):
    """Changement de mot de passe obligatoire à la première connexion."""

    def setUp(self):
        self.utilisateur = Utilisateur.objects.create_user(
            username="dg", password="AncienMotDePasse_2026", role="dg"
        )

    def test_premiere_connexion_signalee_dans_le_profil(self):
        self.client.force_authenticate(self.utilisateur)
        response = self.client.get("/api/auth/me/")
        self.assertTrue(response.data["doit_changer_mot_de_passe"])

    def test_changement_reussi(self):
        self.client.force_authenticate(self.utilisateur)
        response = self.client.post(
            "/api/auth/changer-mot-de-passe/",
            {
                "ancien_mot_de_passe": "AncienMotDePasse_2026",
                "nouveau_mot_de_passe": "NouveauMotDePasse_2026",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.utilisateur.refresh_from_db()
        self.assertFalse(self.utilisateur.doit_changer_mot_de_passe)
        self.assertTrue(self.utilisateur.check_password("NouveauMotDePasse_2026"))

        # La connexion fonctionne avec le nouveau mot de passe
        response = self.client.post(
            "/api/auth/login/",
            {"username": "dg", "password": "NouveauMotDePasse_2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_ancien_mot_de_passe_incorrect_refuse(self):
        self.client.force_authenticate(self.utilisateur)
        response = self.client.post(
            "/api/auth/changer-mot-de-passe/",
            {
                "ancien_mot_de_passe": "faux",
                "nouveau_mot_de_passe": "NouveauMotDePasse_2026",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_mot_de_passe_faible_refuse(self):
        self.client.force_authenticate(self.utilisateur)
        response = self.client.post(
            "/api/auth/changer-mot-de-passe/",
            {
                "ancien_mot_de_passe": "AncienMotDePasse_2026",
                "nouveau_mot_de_passe": "123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class GestionUtilisateursTest(APITestCase):
    """Gestion des comptes par l'administrateur (§5.11)."""

    def setUp(self):
        from services.models import Departement, Service

        self.dept = Departement.objects.create(nom="Ressources Humaines", code="RH")
        self.autre_dept = Departement.objects.create(nom="Finances", code="FIN")
        self.service = Service.objects.create(
            nom="Recrutement", code="RH1", departement=self.dept
        )

        self.admin = Utilisateur.objects.create_user(
            username="admin", password="pass", role="admin"
        )
        self.bo = Utilisateur.objects.create_user(
            username="bureau", password="pass", role="bureau_ordre"
        )

    def test_creation_compte_par_admin(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/utilisateurs/",
            {
                "username": "n.idrissi",
                "first_name": "Nadia",
                "last_name": "Idrissi",
                "email": "n.idrissi@organisation.ma",
                "role": "chef_departement",
                "departement": self.dept.id,
                "mot_de_passe": "MotDePasseInitial_2026",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        cree = Utilisateur.objects.get(username="n.idrissi")
        self.assertEqual(cree.role, "chef_departement")
        self.assertTrue(cree.check_password("MotDePasseInitial_2026"))
        # Changement imposé à la première connexion (§10.1)
        self.assertTrue(cree.doit_changer_mot_de_passe)

    def test_creation_refusee_aux_non_admins(self):
        self.client.force_authenticate(self.bo)
        response = self.client.post(
            "/api/utilisateurs/",
            {"username": "x", "role": "dg", "mot_de_passe": "MotDePasse_2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_coherence_role_et_rattachement(self):
        self.client.force_authenticate(self.admin)

        # Chef de Département sans département : refusé
        response = self.client.post(
            "/api/utilisateurs/",
            {"username": "chef1", "role": "chef_departement", "mot_de_passe": "MotDePasse_2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("departement", response.data)

        # Service n'appartenant pas au département indiqué : refusé
        response = self.client.post(
            "/api/utilisateurs/",
            {
                "username": "chef2",
                "role": "chef_service",
                "departement": self.autre_dept.id,
                "service": self.service.id,
                "mot_de_passe": "MotDePasse_2026",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_desactivation_sans_suppression(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(f"/api/utilisateurs/{self.bo.id}/changer-statut/")
        self.assertEqual(response.status_code, 200)
        self.bo.refresh_from_db()
        self.assertFalse(self.bo.is_active)
        # Le compte existe toujours
        self.assertTrue(Utilisateur.objects.filter(pk=self.bo.pk).exists())

        # Réactivation : le compte désactivé doit rester accessible à l'admin
        response = self.client.post(f"/api/utilisateurs/{self.bo.id}/changer-statut/")
        self.assertEqual(response.status_code, 200)
        self.bo.refresh_from_db()
        self.assertTrue(self.bo.is_active)

    def test_admin_ne_peut_pas_se_desactiver(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/utilisateurs/{self.admin.id}/changer-statut/")
        self.assertEqual(response.status_code, 400)

    def test_suppression_interdite(self):
        self.client.force_authenticate(self.admin)
        response = self.client.delete(f"/api/utilisateurs/{self.bo.id}/")
        self.assertEqual(response.status_code, 405)

    def test_reinitialisation_mot_de_passe_et_deblocage(self):
        self.bo.tentatives_echouees = 3
        self.bo.save()

        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/utilisateurs/{self.bo.id}/",
            {"mot_de_passe": "NouveauMotDePasse_2026"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.bo.refresh_from_db()
        self.assertTrue(self.bo.check_password("NouveauMotDePasse_2026"))
        self.assertTrue(self.bo.doit_changer_mot_de_passe)
        self.assertEqual(self.bo.tentatives_echouees, 0)

    def test_mot_de_passe_faible_refuse(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/utilisateurs/",
            {"username": "faible", "role": "dg", "mot_de_passe": "123"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("mot_de_passe", response.data)
