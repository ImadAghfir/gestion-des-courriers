"""Tests du journal d'activité global (cahier des charges §4.2)."""
from datetime import date

from rest_framework.test import APITestCase

from courriers import services as regles
from services.models import Departement, Service
from utilisateurs.models import Utilisateur


class JournalActiviteTest(APITestCase):
    def setUp(self):
        self.dept = Departement.objects.create(nom="Ressources Humaines", code="RH")
        self.service = Service.objects.create(
            nom="Service S2", code="S2", departement=self.dept
        )

        self.admin = Utilisateur.objects.create_user(
            username="admin", password="pass", role="admin"
        )
        self.bo = Utilisateur.objects.create_user(
            username="bureau", password="pass", role="bureau_ordre"
        )
        self.dg = Utilisateur.objects.create_user(
            username="dg", password="pass", role="dg"
        )
        self.chef_rh = Utilisateur.objects.create_user(
            username="chef_rh", password="pass",
            role="chef_departement", departement=self.dept,
        )

        self.courrier = regles.enregistrer_courrier(
            self.bo,
            dict(
                type_courrier="entrant",
                objet="Demande de subvention",
                numero_source="REF-2026/458",
                date_source=date(2026, 7, 25),
                date_reception=date(2026, 8, 1),
                expediteur="Organisme X",
                categorie="administratif",
            ),
        )
        regles.transmettre_au_dg(self.courrier, self.bo)
        regles.valider_courrier(self.courrier, self.dg)
        regles.affectation_finale(
            self.courrier, self.dg, self.dept, instructions="Traiter vite."
        )

    def test_admin_voit_toutes_les_actions(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/journal/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        # Enregistrement, transmission, validation, affectation finale, instructions
        self.assertGreaterEqual(response.data["count"], 5)

        premiere = response.data["results"][0]
        self.assertIn("auteur_nom", premiere)
        self.assertIn("action_label", premiere)
        self.assertEqual(premiere["courrier_numero"], self.courrier.numero)

    def test_acces_refuse_aux_autres_roles(self):
        for utilisateur in (self.bo, self.dg, self.chef_rh):
            self.client.force_authenticate(utilisateur)
            response = self.client.get("/api/journal/")
            self.assertEqual(response.status_code, 403, utilisateur.username)

    def test_superuser_autorise(self):
        superutilisateur = Utilisateur.objects.create_superuser(
            username="root", password="pass"
        )
        self.client.force_authenticate(superutilisateur)
        self.assertEqual(self.client.get("/api/journal/").status_code, 200)

    def test_filtre_par_action(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/journal/", {"action": "validation"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["action"], "validation")

    def test_filtre_par_utilisateur(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/journal/", {"utilisateur": self.dg.id})

        self.assertGreaterEqual(response.data["count"], 3)
        for entree in response.data["results"]:
            self.assertEqual(entree["auteur"], self.dg.id)

    def test_recherche_libre_et_periode(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get("/api/journal/", {"q": "subvention"})
        self.assertGreaterEqual(response.data["count"], 5)

        response = self.client.get("/api/journal/", {"q": "inexistant-xyz"})
        self.assertEqual(response.data["count"], 0)

        # Période future : aucun résultat
        response = self.client.get("/api/journal/", {"du": "2099-01-01"})
        self.assertEqual(response.data["count"], 0)

        # Date invalide : filtre ignoré, pas d'erreur serveur
        response = self.client.get("/api/journal/", {"du": "pas-une-date"})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 5)

    def test_liste_des_actions_disponibles(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/journal/actions/")

        self.assertEqual(response.status_code, 200)
        valeurs = [action["valeur"] for action in response.data]
        self.assertIn("validation", valeurs)
        self.assertIn("affect_finale", valeurs)

    def test_pagination(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/journal/", {"taille": 2})

        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])
