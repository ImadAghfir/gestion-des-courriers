"""Tests des statistiques et rapports (cahier des charges §5.10)."""
from datetime import date

from rest_framework.test import APITestCase

from courriers import services as regles
from services.models import Departement, Service
from utilisateurs.models import Utilisateur


class StatistiquesApiTest(APITestCase):
    def setUp(self):
        self.dept_rh = Departement.objects.create(nom="Ressources Humaines", code="RH")
        self.dept_fin = Departement.objects.create(nom="Finances", code="FIN")
        self.service_s2 = Service.objects.create(
            nom="Service S2", code="S2", departement=self.dept_rh
        )

        self.bo = Utilisateur.objects.create_user(
            username="bureau", password="pass", role="bureau_ordre"
        )
        self.dg = Utilisateur.objects.create_user(
            username="dg", password="pass", role="dg"
        )
        self.chef_rh = Utilisateur.objects.create_user(
            username="chef_rh", password="pass",
            role="chef_departement", departement=self.dept_rh,
        )
        self.chef_s2 = Utilisateur.objects.create_user(
            username="chef_s2", password="pass",
            role="chef_service", departement=self.dept_rh, service=self.service_s2,
        )
        self.admin = Utilisateur.objects.create_user(
            username="admin", password="pass", role="admin"
        )

        # Un courrier traité de bout en bout
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
                affectations_provisoires=[self.dept_rh],
            ),
        )
        regles.transmettre_au_dg(self.courrier, self.bo)
        regles.valider_courrier(self.courrier, self.dg)
        regles.affectation_finale(
            self.courrier, self.dg, self.dept_rh, instructions="Vite."
        )
        regles.affecter_au_service(self.courrier, self.chef_rh, self.service_s2)
        regles.traiter_courrier(self.courrier, self.chef_s2)
        regles.cloturer_courrier(self.courrier, self.chef_s2)

        # Un second courrier encore au Bureau d'Ordre
        regles.enregistrer_courrier(
            self.bo,
            dict(
                type_courrier="entrant",
                objet="Facture",
                numero_source="FAC-2026/77",
                date_source=date(2026, 8, 1),
                date_reception=date(2026, 8, 5),
                expediteur="Fournisseur Z",
                categorie="financier",
            ),
        )

    def test_statistiques_globales_pour_le_dg(self):
        self.client.force_authenticate(self.dg)
        response = self.client.get("/api/statistiques/")

        self.assertEqual(response.status_code, 200)
        donnees = response.data
        self.assertEqual(donnees["role_rapport"], "global")
        self.assertEqual(donnees["totaux"]["courriers"], 2)
        self.assertEqual(donnees["totaux"]["traites"], 1)
        self.assertEqual(donnees["affectation_provisoire"]["avec"], 1)
        self.assertEqual(donnees["affectation_provisoire"]["sans"], 1)
        self.assertEqual(donnees["avec_instructions"], 1)
        # Délai source → réception : (7 + 4) / 2 = 5.5 jours
        self.assertEqual(donnees["delais"]["source_vers_reception"], 5.5)
        self.assertIsNotNone(donnees["delais"]["traitement_moyen"])
        # Modifications par utilisateur : réservé à l'Admin
        self.assertNotIn("modifications_par_utilisateur", donnees)

    def test_admin_voit_les_modifications_par_utilisateur(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/statistiques/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("modifications_par_utilisateur", response.data)

    def test_chef_departement_voit_son_departement(self):
        self.client.force_authenticate(self.chef_rh)
        response = self.client.get("/api/statistiques/")

        self.assertEqual(response.status_code, 200)
        donnees = response.data
        self.assertEqual(donnees["role_rapport"], "departement")
        self.assertEqual(donnees["totaux"]["courriers"], 1)
        self.assertEqual(donnees["totaux"]["traites"], 1)
        self.assertEqual(donnees["par_service"][0]["label"], "Service S2")

    def test_acces_refuse_aux_autres_roles(self):
        for utilisateur in (self.bo, self.chef_s2):
            self.client.force_authenticate(utilisateur)
            response = self.client.get("/api/statistiques/")
            self.assertEqual(response.status_code, 403)
