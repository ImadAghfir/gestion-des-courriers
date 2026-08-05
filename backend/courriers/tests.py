"""
Tests unitaires pour les règles métier de courriers/services.py.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from courriers.models import Courrier
from courriers import services
from historique.models import Historique
from notifications.models import Notification
from services.models import Service
from utilisateurs.models import Utilisateur


class TransitionEntrantTest(TestCase):
    """Vérifie la machine à états des courriers entrants."""

    def setUp(self):
        self.service = Service.objects.create(nom="DG", code="DG")
        self.user = Utilisateur.objects.create_user(
            username="agent1", password="pass", role="agent", service=self.service
        )
        self.courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Test entrant",
            categorie="Admin",
            createur=self.user,
            service=self.service,
        )
        assert self.courrier.statut == "recu"

    def test_recu_vers_affecte(self):
        services.changer_statut(self.courrier, "affecte", self.user)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, "affecte")

    def test_recu_vers_archive_interdit(self):
        with self.assertRaises(ValidationError):
            services.changer_statut(self.courrier, "archive", self.user)

    def test_en_cours_vers_en_attente_et_retour(self):
        services.changer_statut(self.courrier, "affecte", self.user)
        services.changer_statut(self.courrier, "en_cours", self.user)
        services.changer_statut(self.courrier, "en_attente", self.user)
        services.changer_statut(self.courrier, "en_cours", self.user)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, "en_cours")

    def test_archivage_seulement_depuis_traite(self):
        services.changer_statut(self.courrier, "affecte", self.user)
        services.changer_statut(self.courrier, "en_cours", self.user)
        with self.assertRaises(ValidationError):
            services.changer_statut(self.courrier, "archive", self.user)
        services.changer_statut(self.courrier, "traite", self.user)
        services.changer_statut(self.courrier, "archive", self.user)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, "archive")

    def test_historique_cree_a_chaque_transition(self):
        count_before = Historique.objects.filter(courrier=self.courrier).count()
        services.changer_statut(self.courrier, "affecte", self.user)
        self.assertEqual(
            Historique.objects.filter(courrier=self.courrier).count(),
            count_before + 1,
        )


class TransitionSortantTest(TestCase):
    """Vérifie la machine à états des courriers sortants."""

    def setUp(self):
        self.service = Service.objects.create(nom="RH", code="RH")
        self.responsable = Utilisateur.objects.create_user(
            username="resp", password="pass", role="responsable", service=self.service
        )
        self.service.responsable = self.responsable
        self.service.save()
        self.courrier = Courrier.objects.create(
            type_courrier="sortant",
            objet="Test sortant",
            categorie="RH",
            createur=self.responsable,
            service=self.service,
        )
        assert self.courrier.statut == "brouillon"

    def test_flux_complet_sortant(self):
        services.changer_statut(self.courrier, "en_validation", self.responsable)
        services.changer_statut(self.courrier, "valide", self.responsable)
        services.changer_statut(self.courrier, "envoye", self.responsable)
        services.changer_statut(self.courrier, "archive", self.responsable)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, "archive")

    def test_brouillon_vers_archive_interdit(self):
        with self.assertRaises(ValidationError):
            services.changer_statut(self.courrier, "archive", self.responsable)


class AffectationTest(TestCase):
    """Vérifie les règles d'affectation (Historique + Notification)."""

    def setUp(self):
        self.service = Service.objects.create(nom="IT", code="IT")
        self.auteur = Utilisateur.objects.create_user(
            username="resp_it", password="pass", role="responsable", service=self.service
        )
        self.service.responsable = self.auteur
        self.service.save()
        self.agent = Utilisateur.objects.create_user(
            username="agent_it", password="pass", role="agent", service=self.service
        )
        self.courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Courrier affectation",
            categorie="Admin",
            createur=self.auteur,
            service=self.service,
        )

    def test_affectation_cree_historique(self):
        services.affecter_courrier(self.courrier, self.auteur, utilisateur_cible=self.agent)
        self.assertTrue(
            Historique.objects.filter(
                courrier=self.courrier, action="affectation"
            ).exists()
        )

    def test_affectation_cree_notification_pour_cible(self):
        services.affecter_courrier(self.courrier, self.auteur, utilisateur_cible=self.agent)
        self.assertTrue(
            Notification.objects.filter(
                destinataire=self.agent, courrier=self.courrier
            ).exists()
        )

    def test_affectation_sans_cible_interdit(self):
        with self.assertRaises(ValidationError):
            services.affecter_courrier(self.courrier, self.auteur)

    def test_affectation_passe_statut_recu_en_affecte(self):
        self.assertEqual(self.courrier.statut, "recu")
        services.affecter_courrier(self.courrier, self.auteur, utilisateur_cible=self.agent)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, "affecte")


class UrgenceTest(TestCase):
    """Vérifie les notifications pour les courriers urgents."""

    def setUp(self):
        self.service = Service.objects.create(nom="Urgent", code="URG")
        self.responsable = Utilisateur.objects.create_user(
            username="resp_u", password="pass", role="responsable", service=self.service
        )
        self.service.responsable = self.responsable
        self.service.save()
        self.agent = Utilisateur.objects.create_user(
            username="agent_u", password="pass", role="agent", service=self.service
        )

    def test_courrier_urgent_notifie_responsable(self):
        Notification.objects.all().delete()
        courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Urgent !",
            categorie="Admin",
            priorite="urgent",
            createur=self.agent,
            service=self.service,
        )
        services.notifier_responsable_si_urgent(courrier, declencheur=self.agent)
        self.assertTrue(
            Notification.objects.filter(
                destinataire=self.responsable,
                courrier=courrier,
                type="urgent",
            ).exists()
        )

    def test_courrier_normal_ne_notifie_pas(self):
        Notification.objects.all().delete()
        courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Normal",
            categorie="Admin",
            priorite="normal",
            createur=self.agent,
            service=self.service,
        )
        services.notifier_responsable_si_urgent(courrier, declencheur=self.agent)
        self.assertFalse(
            Notification.objects.filter(destinataire=self.responsable, courrier=courrier).exists()
        )


class NumeroImmuableTest(TestCase):
    """Vérifie que le numéro de courrier est immuable après création."""

    def setUp(self):
        self.service = Service.objects.create(nom="DG2", code="DG2")
        self.user = Utilisateur.objects.create_user(
            username="user2", password="pass", service=self.service
        )

    def test_numero_genere_a_la_creation(self):
        courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Test num",
            categorie="Admin",
            createur=self.user,
            service=self.service,
        )
        self.assertTrue(courrier.numero.startswith("CE-"))

    def test_modification_numero_interdite(self):
        courrier = Courrier.objects.create(
            type_courrier="entrant",
            objet="Test num",
            categorie="Admin",
            createur=self.user,
            service=self.service,
        )
        courrier.numero = "HACK-0001"
        with self.assertRaises(ValidationError):
            courrier.full_clean()
