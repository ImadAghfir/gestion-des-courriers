from datetime import date, timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from courriers.models import Courrier
from services.models import Departement, Service
from utilisateurs.models import Utilisateur

from .models import ControleEcheances, Notification
from .services import verifier_echeances


class NotificationApiTest(APITestCase):
    def setUp(self):
        self.departement = Departement.objects.create(nom="Direction", code="DIR")
        self.service = Service.objects.create(
            nom="Secrétariat", code="SEC", departement=self.departement
        )
        self.user = Utilisateur.objects.create_user(
            username="bureau", password="pass",
            role="bureau_ordre", service=self.service,
        )
        self.other_user = Utilisateur.objects.create_user(
            username="autre", password="pass",
            role="chef_service", service=self.service,
        )
        self.courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Courrier de test",
            numero_source="REF-2026/1",
            date_source=date(2026, 8, 1),
            date_reception=date(2026, 8, 2),
            expediteur="Organisme X",
            categorie="administratif",
            createur=self.user,
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


class AlertesEcheancesTest(APITestCase):
    """§5.9 — Rappel J-2 et alerte courrier en retard."""

    def setUp(self):
        self.dept = Departement.objects.create(nom="Ressources Humaines", code="RH")
        self.service = Service.objects.create(
            nom="Service S2", code="S2", departement=self.dept
        )
        self.bo = Utilisateur.objects.create_user(
            username="bureau", password="pass", role="bureau_ordre"
        )
        self.dg = Utilisateur.objects.create_user(
            username="dg", password="pass", role="dg"
        )
        self.chef_dept = Utilisateur.objects.create_user(
            username="chef_rh", password="pass",
            role="chef_departement", departement=self.dept,
        )
        self.chef_service = Utilisateur.objects.create_user(
            username="chef_s2", password="pass",
            role="chef_service", departement=self.dept, service=self.service,
        )
        self.aujourd_hui = timezone.now().date()

    def _creer_courrier(self, echeance, **kwargs):
        donnees = dict(
            type_courrier="entrant",
            objet="Courrier à échéance",
            numero_source="REF-2026/1",
            date_source=date(2026, 8, 1),
            date_reception=date(2026, 8, 2),
            expediteur="X",
            categorie="administratif",
            createur=self.bo,
            date_echeance=echeance,
        )
        donnees.update(kwargs)
        return Courrier.objects.create(**donnees)

    def test_rappel_j2_au_responsable(self):
        # Courrier affecté au service, échéance dans 2 jours
        self._creer_courrier(
            self.aujourd_hui + timedelta(days=2),
            statut="en_traitement",
            departement=self.dept,
            service=self.service,
        )

        rappels, retards = verifier_echeances()
        self.assertEqual((rappels, retards), (1, 0))

        notification = Notification.objects.get(destinataire=self.chef_service)
        self.assertTrue(notification.message.startswith("[Rappel J-2]"))
        self.assertEqual(notification.type, "warning")

    def test_alerte_retard_dg_et_chef_dept(self):
        self._creer_courrier(
            self.aujourd_hui - timedelta(days=3),
            statut="affecte",
            departement=self.dept,
        )

        rappels, retards = verifier_echeances()
        self.assertEqual((rappels, retards), (0, 2))  # DG + Chef Dept

        for destinataire in (self.dg, self.chef_dept):
            notification = Notification.objects.get(destinataire=destinataire)
            self.assertTrue(notification.message.startswith("[RETARD]"))
            self.assertEqual(notification.type, "urgent")

    def test_pas_de_doublon_le_meme_jour(self):
        self._creer_courrier(
            self.aujourd_hui - timedelta(days=1),
            statut="affecte",
            departement=self.dept,
        )

        verifier_echeances()
        rappels, retards = verifier_echeances()  # deuxième passage
        self.assertEqual((rappels, retards), (0, 0))

    def test_courriers_termines_ignores(self):
        self._creer_courrier(
            self.aujourd_hui - timedelta(days=5),
            statut="traite",
            departement=self.dept,
        )
        rappels, retards = verifier_echeances()
        self.assertEqual((rappels, retards), (0, 0))

    def test_declenchement_via_liste_notifications(self):
        self._creer_courrier(
            self.aujourd_hui + timedelta(days=1),
            statut="enregistre",
        )
        # Sans service ni département : le créateur (BO) est le responsable
        self.client.force_authenticate(self.bo)
        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Notification.objects.filter(
                destinataire=self.bo, message__startswith="[Rappel J-2]"
            ).exists()
        )

        # Le contrôle est limité à une exécution par heure
        self.assertFalse(ControleEcheances.doit_executer(intervalle_minutes=60))


class CorrectionsNotificationsTest(APITestCase):
    """Défauts identifiés lors de l'audit du système de notifications."""

    def setUp(self):
        self.dept = Departement.objects.create(nom="Ressources Humaines", code="RH")
        self.bo = Utilisateur.objects.create_user(
            username="bureau", password="pass", role="bureau_ordre"
        )
        self.dg = Utilisateur.objects.create_user(
            username="dg", password="pass", role="dg"
        )
        self.chef = Utilisateur.objects.create_user(
            username="chef_rh", password="pass",
            role="chef_departement", departement=self.dept,
        )
        self.hier = timezone.now().date() - timedelta(days=3)

    def test_courrier_sortant_envoye_pas_signale_en_retard(self):
        """Un courrier sortant déjà expédié n'a plus d'échéance à tenir."""
        from courriers import services as regles

        courrier = regles.enregistrer_courrier(
            self.bo,
            dict(
                type_courrier="sortant",
                objet="Réponse expédiée",
                numero_source="DEP-2026/9",
                date_source=date(2026, 8, 1),
                destinataire="Organisme Y",
                categorie="reponse",
                date_echeance=self.hier,
            ),
        )
        regles.valider_courrier(courrier, self.dg)
        regles.envoyer_courrier(courrier, self.bo)

        Notification.objects.all().delete()
        rappels, retards = verifier_echeances()

        self.assertEqual(retards, 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_pas_d_alerte_pour_un_compte_desactive(self):
        from courriers import services as regles

        courrier = regles.enregistrer_courrier(
            self.bo,
            dict(
                type_courrier="entrant",
                objet="Courrier en retard",
                numero_source="REF-2026/9",
                date_source=date(2026, 8, 1),
                date_reception=date(2026, 8, 2),
                expediteur="X",
                categorie="administratif",
                date_echeance=self.hier,
            ),
        )
        regles.transmettre_au_dg(courrier, self.bo)
        regles.valider_courrier(courrier, self.dg)
        regles.affectation_finale(courrier, self.dg, self.dept)

        self.chef.is_active = False
        self.chef.save()
        Notification.objects.all().delete()

        verifier_echeances()

        destinataires = {n.destinataire.username for n in Notification.objects.all()}
        self.assertNotIn("chef_rh", destinataires)
        self.assertIn("dg", destinataires)

    def test_compteur_de_non_lues(self):
        for numero in range(3):
            Notification.objects.create(
                destinataire=self.dg, message=f"Message {numero}"
            )
        Notification.objects.create(destinataire=self.dg, message="Lue", lu=True)
        Notification.objects.create(destinataire=self.bo, message="Autre utilisateur")

        self.client.force_authenticate(self.dg)
        response = self.client.get("/api/notifications/compteur/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["non_lues"], 3)
        self.assertEqual(response.data["total"], 4)

    def test_tout_marquer_comme_lues(self):
        for numero in range(5):
            Notification.objects.create(
                destinataire=self.dg, message=f"Message {numero}"
            )
        Notification.objects.create(destinataire=self.bo, message="Autre utilisateur")

        self.client.force_authenticate(self.dg)
        response = self.client.post("/api/notifications/tout-marquer-lues/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(destinataire=self.dg, lu=False).count(), 0
        )
        # Les notifications des autres utilisateurs ne sont pas touchées
        self.assertEqual(
            Notification.objects.filter(destinataire=self.bo, lu=False).count(), 1
        )

    def test_liste_limitee_aux_plus_recentes(self):
        for numero in range(60):
            Notification.objects.create(
                destinataire=self.dg, message=f"Message {numero}"
            )

        self.client.force_authenticate(self.dg)

        response = self.client.get("/api/notifications/")
        self.assertEqual(len(response.data), 50)

        response = self.client.get("/api/notifications/", {"limite": 10})
        self.assertEqual(len(response.data), 10)

        # Une limite absurde est ramenée au maximum autorisé
        response = self.client.get("/api/notifications/", {"limite": 99999})
        self.assertEqual(len(response.data), 60)

        # Une limite non numérique n'entraîne pas d'erreur
        response = self.client.get("/api/notifications/", {"limite": "abc"})
        self.assertEqual(response.status_code, 200)

    def test_purge_des_notifications_lues_anciennes(self):
        from notifications.services import purger_notifications_lues

        ancienne_lue = Notification.objects.create(
            destinataire=self.dg, message="Ancienne lue", lu=True
        )
        ancienne_non_lue = Notification.objects.create(
            destinataire=self.dg, message="Ancienne non lue", lu=False
        )
        recente = Notification.objects.create(
            destinataire=self.dg, message="Récente", lu=True
        )

        vieille_date = timezone.now() - timedelta(days=120)
        Notification.objects.filter(
            pk__in=[ancienne_lue.pk, ancienne_non_lue.pk]
        ).update(date=vieille_date)

        supprimees = purger_notifications_lues(jours=90)

        self.assertEqual(supprimees, 1)
        self.assertFalse(Notification.objects.filter(pk=ancienne_lue.pk).exists())
        # Une notification non lue n'est jamais supprimée
        self.assertTrue(Notification.objects.filter(pk=ancienne_non_lue.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=recente.pk).exists())

    def test_liste_accessible_meme_si_le_controle_echeances_echoue(self):
        """Une panne du contrôle d'échéances ne doit pas bloquer la consultation."""
        from unittest.mock import patch

        Notification.objects.create(destinataire=self.dg, message="Visible")
        self.client.force_authenticate(self.dg)

        with patch(
            "notifications.views.verifier_echeances",
            side_effect=RuntimeError("panne simulée"),
        ):
            with self.assertLogs("notifications.views", level="ERROR"):
                response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
