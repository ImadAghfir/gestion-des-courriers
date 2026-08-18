"""
Tests des règles métier du cahier des charges v3.3 :
affectation provisoire (AP), affectation finale (AF), instructions (RI),
modifications (RM) et retour au DG (RR).
"""
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase

from courriers import services as regles
from courriers.models import Courrier
from historique.models import Historique
from notifications.models import Notification
from services.models import Departement, Service
from utilisateurs.models import Utilisateur


def creer_organisation():
    """Crée une petite organisation de test : 2 départements, 2 services, 5 acteurs."""
    dept_rh = Departement.objects.create(nom="Ressources Humaines", code="RH")
    dept_fin = Departement.objects.create(nom="Finances", code="FIN")
    service_s2 = Service.objects.create(nom="Service S2", code="S2", departement=dept_rh)
    service_fin1 = Service.objects.create(nom="Comptabilité", code="FIN1", departement=dept_fin)

    acteurs = {
        "bo": Utilisateur.objects.create_user(
            username="bureau", password="pass", role="bureau_ordre"
        ),
        "dg": Utilisateur.objects.create_user(
            username="dg", password="pass", role="dg"
        ),
        "chef_rh": Utilisateur.objects.create_user(
            username="chef_rh", password="pass",
            role="chef_departement", departement=dept_rh,
        ),
        "chef_fin": Utilisateur.objects.create_user(
            username="chef_fin", password="pass",
            role="chef_departement", departement=dept_fin,
        ),
        "chef_s2": Utilisateur.objects.create_user(
            username="chef_s2", password="pass",
            role="chef_service", departement=dept_rh, service=service_s2,
        ),
        "admin": Utilisateur.objects.create_user(
            username="admin", password="pass", role="admin"
        ),
    }
    return dept_rh, dept_fin, service_s2, service_fin1, acteurs


def creer_courrier_entrant(bo, **kwargs):
    donnees = dict(
        type_courrier="entrant",
        objet="Demande de subvention",
        numero_source="REF-2026/458",
        date_source=date(2026, 7, 25),
        date_reception=date(2026, 8, 1),
        expediteur="Organisme X",
        categorie="administratif",
    )
    donnees.update(kwargs)
    return regles.enregistrer_courrier(bo, donnees)


class EnregistrementTest(TestCase):
    """§5.3.2 / §5.3.3 — Enregistrement et affectation provisoire."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()

    def test_numero_interne_genere_automatiquement(self):
        courrier = creer_courrier_entrant(self.acteurs["bo"])
        annee = date.today().year
        self.assertEqual(courrier.numero, f"CE-{annee}-00001")
        self.assertEqual(courrier.statut, "enregistre")

    def test_seul_le_bureau_d_ordre_enregistre(self):
        with self.assertRaises(PermissionDenied):
            creer_courrier_entrant(self.acteurs["dg"])
        with self.assertRaises(PermissionDenied):
            creer_courrier_entrant(self.acteurs["chef_rh"])

    def test_affectation_provisoire_optionnelle_et_tracee(self):
        """Règles AP-01 et AP-05."""
        courrier = creer_courrier_entrant(
            self.acteurs["bo"], affectation_provisoire=self.dept_rh
        )
        self.assertEqual(courrier.statut, "affect_provisoire")
        self.assertTrue(
            Historique.objects.filter(
                courrier=courrier, action="affect_provisoire"
            ).exists()
        )

    def test_numero_source_et_date_source_immuables(self):
        """Règle RM-01."""
        courrier = creer_courrier_entrant(self.acteurs["bo"])
        courrier.numero_source = "AUTRE-999"
        with self.assertRaises(ValidationError):
            courrier.full_clean()


class WorkflowEntrantTest(TestCase):
    """§5.3.9 — Cycle de vie complet d'un courrier entrant."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()
        self.courrier = creer_courrier_entrant(
            self.acteurs["bo"], affectation_provisoire=self.dept_rh
        )

    def test_cycle_complet(self):
        bo, dg = self.acteurs["bo"], self.acteurs["dg"]
        chef_rh, chef_s2 = self.acteurs["chef_rh"], self.acteurs["chef_s2"]

        regles.transmettre_au_dg(self.courrier, bo)
        self.assertEqual(self.courrier.statut, "transmis")

        regles.valider_courrier(self.courrier, dg)
        self.assertEqual(self.courrier.statut, "valide")

        regles.affectation_finale(
            self.courrier, dg, self.dept_rh,
            instructions="Répondre avant le 10/08. Contacter M. Dupont.",
        )
        self.assertEqual(self.courrier.statut, "affecte")
        self.assertEqual(self.courrier.departement, self.dept_rh)
        self.assertEqual(
            self.courrier.instructions_dg,
            "Répondre avant le 10/08. Contacter M. Dupont.",
        )

        regles.affecter_au_service(
            self.courrier, chef_rh, self.service_s2,
            instructions="Préparer un projet de réponse.",
        )
        self.assertEqual(self.courrier.service, self.service_s2)

        regles.traiter_courrier(self.courrier, chef_s2)
        self.assertEqual(self.courrier.statut, "en_traitement")

        regles.cloturer_courrier(self.courrier, chef_s2)
        self.assertEqual(self.courrier.statut, "traite")

        regles.archiver_courrier(self.courrier, bo)
        self.assertEqual(self.courrier.statut, "archive")

    def test_transitions_interdites(self):
        # Pas d'archivage avant traitement
        with self.assertRaises(ValidationError):
            regles.archiver_courrier(self.courrier, self.acteurs["bo"])
        # Pas de validation avant transmission
        with self.assertRaises(ValidationError):
            regles.valider_courrier(self.courrier, self.acteurs["dg"])

    def test_rejet_exige_un_commentaire(self):
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        with self.assertRaises(ValidationError):
            regles.rejeter_courrier(self.courrier, self.acteurs["dg"], "  ")
        regles.rejeter_courrier(self.courrier, self.acteurs["dg"], "Dossier incomplet.")
        self.assertEqual(self.courrier.statut, "rejete")
        # Le Bureau d'Ordre peut retransmettre après correction
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        self.assertEqual(self.courrier.statut, "transmis")


class AffectationFinaleTest(TestCase):
    """Règles AF-01 à AF-06."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()
        self.courrier = creer_courrier_entrant(
            self.acteurs["bo"], affectation_provisoire=self.dept_rh
        )
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])

    def test_af01_seul_le_dg_affecte(self):
        for acteur in ("bo", "chef_rh", "chef_s2"):
            with self.assertRaises(PermissionDenied):
                regles.affectation_finale(
                    self.courrier, self.acteurs[acteur], self.dept_rh
                )

    def test_af03_le_dg_peut_ignorer_la_provisoire(self):
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_fin)
        self.assertEqual(self.courrier.departement, self.dept_fin)
        # L'affectation provisoire reste conservée pour traçabilité
        self.assertEqual(self.courrier.affectation_provisoire, self.dept_rh)

    def test_af06_affectation_finale_tracee(self):
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)
        entree = Historique.objects.get(courrier=self.courrier, action="affect_finale")
        self.assertIn("provisoire acceptée", entree.commentaire)

    def test_notification_chef_departement(self):
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)
        self.assertTrue(
            Notification.objects.filter(
                destinataire=self.acteurs["chef_rh"], courrier=self.courrier
            ).exists()
        )
        # Le chef de l'autre département n'est pas notifié
        self.assertFalse(
            Notification.objects.filter(
                destinataire=self.acteurs["chef_fin"], courrier=self.courrier
            ).exists()
        )


class RetourAuDGTest(TestCase):
    """Règles RR-01 à RR-06."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()
        self.courrier = creer_courrier_entrant(self.acteurs["bo"])
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)

    def test_rr02_commentaire_obligatoire(self):
        with self.assertRaises(ValidationError):
            regles.retourner_au_dg(self.courrier, self.acteurs["chef_rh"], "")

    def test_retour_puis_reaffectation(self):
        regles.retourner_au_dg(
            self.courrier, self.acteurs["chef_rh"], "Ce courrier ne me concerne pas."
        )
        self.assertEqual(self.courrier.statut, "retourne_dg")

        # RR-03 : notification immédiate au DG
        self.assertTrue(
            Notification.objects.filter(
                destinataire=self.acteurs["dg"],
                courrier=self.courrier,
                type="urgent",
            ).exists()
        )

        # Réaffectation par le DG vers le bon département
        regles.affectation_finale(
            self.courrier, self.acteurs["dg"], self.dept_fin,
            instructions="Merci de traiter rapidement.",
        )
        self.assertEqual(self.courrier.statut, "affecte")
        self.assertEqual(self.courrier.departement, self.dept_fin)
        self.assertTrue(
            Historique.objects.filter(
                courrier=self.courrier, action="reaffectation"
            ).exists()
        )

    def test_seul_le_chef_du_departement_concerne_retourne(self):
        with self.assertRaises(PermissionDenied):
            regles.retourner_au_dg(
                self.courrier, self.acteurs["chef_fin"], "Pas pour moi."
            )

    def test_chef_departement_ne_reaffecte_pas_vers_autre_departement(self):
        """§4.5 — un Chef de Département ne peut pas réaffecter ailleurs."""
        with self.assertRaises(ValidationError):
            regles.affecter_au_service(
                self.courrier, self.acteurs["chef_rh"], self.service_fin1
            )


class InstructionsTest(TestCase):
    """Règles RI-01 à RI-05."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()
        self.courrier = creer_courrier_entrant(self.acteurs["bo"])
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)

    def test_ri04_instructions_dg_reservees_au_dg(self):
        with self.assertRaises(PermissionDenied):
            regles.donner_instructions_dg(
                self.courrier, self.acteurs["chef_rh"], "Test"
            )

    def test_ri05_modification_instruction_tracee(self):
        regles.donner_instructions_dg(self.courrier, self.acteurs["dg"], "Version 1")
        regles.donner_instructions_dg(self.courrier, self.acteurs["dg"], "Version 2")

        entrees = Historique.objects.filter(
            courrier=self.courrier, action="instructions_dg"
        ).order_by("date")
        self.assertEqual(entrees.count(), 2)
        derniere = entrees.last()
        self.assertEqual(derniere.ancienne_valeur, "Version 1")
        self.assertEqual(derniere.nouvelle_valeur, "Version 2")

    def test_instructions_chef_dept_notifiees_au_chef_service(self):
        regles.affecter_au_service(
            self.courrier, self.acteurs["chef_rh"], self.service_s2
        )
        regles.donner_instructions_chef_dept(
            self.courrier, self.acteurs["chef_rh"], "Priorité haute."
        )
        self.assertTrue(
            Notification.objects.filter(
                destinataire=self.acteurs["chef_s2"],
                courrier=self.courrier,
                message__icontains="Instructions du Chef de Département",
            ).exists()
        )


class ModificationTest(TestCase):
    """Règles RM-01 à RM-06."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()
        self.courrier = creer_courrier_entrant(self.acteurs["bo"])

    def test_rm01_champs_immuables(self):
        for champ, valeur in (
            ("numero", "CE-2099-99999"),
            ("numero_source", "AUTRE"),
            ("date_source", date(2020, 1, 1)),
            ("date_reception", date(2020, 1, 1)),
        ):
            with self.assertRaises(ValidationError):
                regles.modifier_courrier(
                    self.courrier, self.acteurs["bo"], {champ: valeur}
                )

    def test_rm02_bureau_d_ordre_avant_validation_uniquement(self):
        # Avant validation : autorisé
        regles.modifier_courrier(
            self.courrier, self.acteurs["bo"], {"objet": "Objet corrigé"}
        )
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.objet, "Objet corrigé")

        # Après validation : refusé
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        with self.assertRaises(ValidationError):
            regles.modifier_courrier(
                self.courrier, self.acteurs["bo"], {"objet": "Trop tard"}
            )

    def test_rm05_historique_conserve_les_valeurs(self):
        regles.modifier_courrier(
            self.courrier,
            self.acteurs["bo"],
            {"priorite": "urgent"},
            commentaire="Délai serré.",
        )
        entree = Historique.objects.get(
            courrier=self.courrier, action="modification"
        )
        self.assertEqual(entree.champ_modifie, "priorite")
        self.assertEqual(entree.ancienne_valeur, "normal")
        self.assertEqual(entree.nouvelle_valeur, "urgent")
        self.assertEqual(entree.commentaire, "Délai serré.")

    def test_rm03_dg_avant_affectation_au_service(self):
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)

        # Avant affectation au service : autorisé
        regles.modifier_courrier(
            self.courrier, self.acteurs["dg"], {"priorite": "urgent"}
        )

        # Après affectation au service : refusé
        regles.affecter_au_service(
            self.courrier, self.acteurs["chef_rh"], self.service_s2
        )
        with self.assertRaises(ValidationError):
            regles.modifier_courrier(
                self.courrier, self.acteurs["dg"], {"priorite": "normal"}
            )

    def test_chef_service_ne_modifie_pas_les_champs(self):
        with self.assertRaises((PermissionDenied, ValidationError)):
            regles.modifier_courrier(
                self.courrier, self.acteurs["chef_s2"], {"objet": "Interdit"}
            )

    def test_courrier_archive_non_modifiable(self):
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)
        regles.affecter_au_service(
            self.courrier, self.acteurs["chef_rh"], self.service_s2
        )
        regles.traiter_courrier(self.courrier, self.acteurs["chef_s2"])
        regles.cloturer_courrier(self.courrier, self.acteurs["chef_s2"])
        regles.archiver_courrier(self.courrier, self.acteurs["bo"])

        with self.assertRaises(ValidationError):
            regles.ajouter_commentaire(
                self.courrier, self.acteurs["bo"], "Trop tard."
            )


class CourrierSortantTest(TestCase):
    """§5.4 — Cycle de vie d'un courrier sortant."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()
        self.courrier = regles.enregistrer_courrier(
            self.acteurs["bo"],
            dict(
                type_courrier="sortant",
                objet="Réponse à la demande",
                numero_source="DEP-2026/12",
                date_source=date(2026, 8, 5),
                destinataire="Organisme X",
                categorie="reponse",
            ),
        )

    def test_numero_prefixe_cs(self):
        annee = date.today().year
        self.assertEqual(self.courrier.numero, f"CS-{annee}-00001")
        self.assertEqual(self.courrier.statut, "enregistre")

    def test_cycle_sortant(self):
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.envoyer_courrier(self.courrier, self.acteurs["bo"])
        regles.archiver_courrier(self.courrier, self.acteurs["bo"])
        self.assertEqual(self.courrier.statut, "archive")


class VisibiliteApiTest(APITestCase):
    """§5.3.4 / §10.3 — Périmètres de consultation et visibilité des champs."""

    def setUp(self):
        (self.dept_rh, self.dept_fin, self.service_s2,
         self.service_fin1, self.acteurs) = creer_organisation()
        self.courrier = creer_courrier_entrant(
            self.acteurs["bo"], affectation_provisoire=self.dept_rh
        )

    def _detail(self, acteur):
        self.client.force_authenticate(self.acteurs[acteur])
        return self.client.get(f"/api/courriers/{self.courrier.id}/")

    def test_ap03_affectation_provisoire_cachee_aux_chefs(self):
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)

        # Visible pour le DG
        response = self._detail("dg")
        self.assertIn("affectation_provisoire", response.data)

        # Invisible pour le Chef de Département
        response = self._detail("chef_rh")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("affectation_provisoire", response.data)
        # Instructions DG visibles par le Chef de Département (RI-01)
        self.assertIn("instructions_dg", response.data)

    def test_perimetre_chef_departement(self):
        # Avant l'affectation finale, le Chef de Département ne voit rien
        self.client.force_authenticate(self.acteurs["chef_rh"])
        response = self.client.get("/api/courriers/")
        self.assertEqual(len(response.data), 0)

        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)

        response = self.client.get("/api/courriers/")
        self.assertEqual(len(response.data), 1)

        # Le chef de l'autre département ne voit toujours rien
        self.client.force_authenticate(self.acteurs["chef_fin"])
        response = self.client.get("/api/courriers/")
        self.assertEqual(len(response.data), 0)

    def test_api_creation_et_workflow(self):
        """Scénario API complet : enregistrement → archivage."""
        self.client.force_authenticate(self.acteurs["bo"])
        response = self.client.post(
            "/api/courriers/",
            {
                "type_courrier": "entrant",
                "objet": "Courrier API",
                "numero_source": "REF-2026/900",
                "date_source": "2026-08-01",
                "date_reception": "2026-08-10",
                "expediteur": "Partenaire Y",
                "categorie": "financier",
                "affectation_provisoire": self.dept_fin.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        courrier_id = response.data["id"]
        self.assertEqual(response.data["statut"], "affect_provisoire")

        # Transmission
        response = self.client.post(f"/api/courriers/{courrier_id}/transmettre/")
        self.assertEqual(response.status_code, 200)

        # Le Bureau d'Ordre ne peut pas valider
        response = self.client.post(f"/api/courriers/{courrier_id}/valider/")
        self.assertEqual(response.status_code, 403)

        # Validation + affectation finale par le DG
        self.client.force_authenticate(self.acteurs["dg"])
        response = self.client.post(f"/api/courriers/{courrier_id}/valider/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            f"/api/courriers/{courrier_id}/affectation-finale/",
            {"departement_id": self.dept_fin.id, "instructions": "Vérifier le budget."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["departement"], self.dept_fin.id)

        # Retour au DG sans commentaire → refusé (RR-02)
        self.client.force_authenticate(self.acteurs["chef_fin"])
        response = self.client.post(
            f"/api/courriers/{courrier_id}/retourner-dg/", {"commentaire": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_recherche_avancee(self):
        """§5.7 — filtres de recherche."""
        # Deuxième courrier pour distinguer les résultats
        creer_courrier_entrant(
            self.acteurs["bo"],
            objet="Facture fournisseur",
            numero_source="FAC-2026/77",
            priorite="urgent",
            date_reception=date(2026, 6, 15),
            categorie="financier",
        )
        self.client.force_authenticate(self.acteurs["dg"])

        # Recherche texte sur le numéro source
        response = self.client.get("/api/courriers/", {"q": "FAC-2026"})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["numero_source"], "FAC-2026/77")

        # Recherche texte sur l'objet
        response = self.client.get("/api/courriers/", {"q": "subvention"})
        self.assertEqual(len(response.data), 1)

        # Filtre par priorité
        response = self.client.get("/api/courriers/", {"priorite": "urgent"})
        self.assertEqual(len(response.data), 1)

        # Filtre par catégorie
        response = self.client.get("/api/courriers/", {"categorie": "financier"})
        self.assertEqual(len(response.data), 1)

        # Période de réception
        response = self.client.get(
            "/api/courriers/", {"reception_du": "2026-07-01"}
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["numero_source"], "REF-2026/458")

        # Date invalide : filtre ignoré sans erreur serveur
        response = self.client.get(
            "/api/courriers/", {"reception_du": "pas-une-date"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

        # Avec / sans instructions
        courrier = Courrier.objects.get(numero_source="REF-2026/458")
        regles.transmettre_au_dg(courrier, self.acteurs["bo"])
        regles.valider_courrier(courrier, self.acteurs["dg"])
        regles.affectation_finale(
            courrier, self.acteurs["dg"], self.dept_rh, instructions="Urgent."
        )
        response = self.client.get("/api/courriers/", {"avec_instructions": "oui"})
        self.assertEqual(len(response.data), 1)
        response = self.client.get("/api/courriers/", {"avec_instructions": "non"})
        self.assertEqual(len(response.data), 1)

        # Filtre par département
        response = self.client.get(
            "/api/courriers/", {"departement": self.dept_rh.id}
        )
        self.assertEqual(len(response.data), 1)

    def test_recherche_respecte_le_perimetre(self):
        """La recherche ne contourne pas le périmètre de consultation."""
        regles.transmettre_au_dg(self.courrier, self.acteurs["bo"])
        regles.valider_courrier(self.courrier, self.acteurs["dg"])
        regles.affectation_finale(self.courrier, self.acteurs["dg"], self.dept_rh)

        # Le chef FIN cherche un courrier du département RH : aucun résultat
        self.client.force_authenticate(self.acteurs["chef_fin"])
        response = self.client.get("/api/courriers/", {"q": "subvention"})
        self.assertEqual(len(response.data), 0)

    def test_creation_sans_numero_source_refusee(self):
        self.client.force_authenticate(self.acteurs["bo"])
        response = self.client.post(
            "/api/courriers/",
            {
                "type_courrier": "entrant",
                "objet": "Sans numéro source",
                "date_source": "2026-08-01",
                "date_reception": "2026-08-10",
                "expediteur": "X",
                "categorie": "autre",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("numero_source", response.data)
