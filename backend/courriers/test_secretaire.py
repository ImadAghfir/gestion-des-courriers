"""
Tests unitaires pour le rôle Secrétaire — Cahier des Charges v4.0 (Règle R-01).

Vérifie que le Secrétaire dispose exactement des mêmes droits et fonctionnalités
que le Directeur Général :
- validation et rejet des courriers ;
- affectation finale et réaffectation ;
- instructions de direction ;
- modification contrôlée des courriers ;
- accès à tous les courriers dans le queryset ;
- accès aux statistiques globales ;
- réception des notifications de transmission et de retour ;
- interdiction d'enregistrer un courrier (réservé au Bureau d'Ordre).
"""
from datetime import date
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from utilisateurs.models import Utilisateur
from services.models import Departement, Service
from courriers.models import Courrier
from notifications.models import Notification
from courriers import services


class SecretaireRoleTest(APITestCase):

    def setUp(self):
        self.dept_rh = Departement.objects.create(code="RH", nom="Ressources Humaines")
        self.dept_fin = Departement.objects.create(code="FIN", nom="Finances")
        self.serv_recrutement = Service.objects.create(
            code="RH1", nom="Recrutement", departement=self.dept_rh
        )

        self.user_bureau = Utilisateur.objects.create_user(
            username="bureau", password="pass_2026", role=Utilisateur.Role.BUREAU_ORDRE
        )
        self.user_dg = Utilisateur.objects.create_user(
            username="dg", password="pass_2026", role=Utilisateur.Role.DG
        )
        self.user_secretaire = Utilisateur.objects.create_user(
            username="secretaire", password="pass_2026", role=Utilisateur.Role.SECRETAIRE
        )
        self.user_chef_rh = Utilisateur.objects.create_user(
            username="chef_rh", password="pass_2026", role=Utilisateur.Role.CHEF_DEPARTEMENT,
            departement=self.dept_rh
        )

    def _creer_entrant_transmis(self):
        courrier = Courrier.objects.create(
            type_courrier=Courrier.TypeCourrier.ENTRANT,
            numero_source="SRC-001",
            date_source=date(2026, 1, 15),
            date_reception=date(2026, 1, 16),
            objet="Demande officielle",
            expediteur="Ministère",
            statut=Courrier.Statut.TRANSMIS,
            createur=self.user_bureau,
        )
        return courrier

    def test_secretaire_peut_valider_courrier(self):
        courrier = self._creer_entrant_transmis()
        services.valider_courrier(courrier, self.user_secretaire, commentaire="Validé par la secrétaire")
        courrier.refresh_from_db()
        self.assertEqual(courrier.statut, "valide")

    def test_secretaire_peut_rejeter_courrier(self):
        courrier = self._creer_entrant_transmis()
        services.rejeter_courrier(courrier, self.user_secretaire, commentaire="Document illisible")
        courrier.refresh_from_db()
        self.assertEqual(courrier.statut, "rejete")

    def test_secretaire_peut_affecter_finalement(self):
        courrier = self._creer_entrant_transmis()
        services.valider_courrier(courrier, self.user_secretaire)
        services.affectation_finale(
            courrier, self.user_secretaire, self.dept_rh,
            instructions="À traiter sous 48h"
        )
        courrier.refresh_from_db()
        self.assertEqual(courrier.statut, "affecte")
        self.assertEqual(courrier.departement, self.dept_rh)
        self.assertEqual(courrier.instructions_dg, "À traiter sous 48h")

    def test_secretaire_peut_donner_instructions(self):
        courrier = self._creer_entrant_transmis()
        services.valider_courrier(courrier, self.user_secretaire)
        services.affectation_finale(courrier, self.user_secretaire, self.dept_rh)
        services.donner_instructions_dg(courrier, self.user_secretaire, "Instructions modifiées")
        courrier.refresh_from_db()
        self.assertEqual(courrier.instructions_dg, "Instructions modifiées")

    def test_secretaire_recoit_notifications_transmission_et_retour(self):
        courrier = Courrier.objects.create(
            type_courrier=Courrier.TypeCourrier.ENTRANT,
            numero_source="SRC-002",
            date_source=date(2026, 1, 15),
            date_reception=date(2026, 1, 16),
            objet="Notification test",
            expediteur="Partenaire",
            statut=Courrier.Statut.ENREGISTRE,
            createur=self.user_bureau,
        )
        # Transmission
        services.transmettre_au_dg(courrier, self.user_bureau)
        notif_secretaire = Notification.objects.filter(
            destinataire=self.user_secretaire, courrier=courrier
        ).first()
        self.assertIsNotNone(notif_secretaire)

        # Validation + Affectation + Retour
        services.valider_courrier(courrier, self.user_secretaire)
        services.affectation_finale(courrier, self.user_secretaire, self.dept_rh)
        services.retourner_au_dg(courrier, self.user_chef_rh, commentaire="Mauvais département")

        notifs_retour = Notification.objects.filter(
            destinataire=self.user_secretaire, courrier=courrier, type=Notification.Type.URGENT
        )
        self.assertTrue(notifs_retour.exists())

    def test_secretaire_ne_peut_pas_enregistrer_courrier(self):
        self.client.force_authenticate(self.user_secretaire)
        reponse = self.client.post(
            "/api/courriers/",
            {
                "type_courrier": "entrant",
                "numero_source": "SRC-999",
                "date_source": "2026-02-01",
                "date_reception": "2026-02-02",
                "objet": "Test enregistrement",
                "expediteur": "Externe",
                "priorite": "normal",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_secretaire_voit_tous_les_courriers_et_statistiques_globales(self):
        c1 = self._creer_entrant_transmis()
        c2 = Courrier.objects.create(
            type_courrier=Courrier.TypeCourrier.SORTANT,
            numero_source="OUT-001",
            date_source=date(2026, 1, 15),
            objet="Courrier sortant",
            destinataire="Fournisseur",
            statut=Courrier.Statut.ENREGISTRE,
            createur=self.user_bureau,
        )

        self.client.force_authenticate(self.user_secretaire)
        rep_courriers = self.client.get("/api/courriers/")
        self.assertEqual(rep_courriers.status_code, status.HTTP_200_OK)
        # Secretaire voit tous les courriers
        ids_recus = [c["id"] for c in rep_courriers.data]
        self.assertIn(c1.id, ids_recus)
        self.assertIn(c2.id, ids_recus)

        # Secretaire a accès aux statistiques globales
        rep_stats = self.client.get("/api/statistiques/")
        self.assertEqual(rep_stats.status_code, status.HTTP_200_OK)
        self.assertEqual(rep_stats.data.get("role_rapport"), "global")
