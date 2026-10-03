import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, mock_open, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from utilisateurs.models import Utilisateur
from courriers import ai


class AnalyseDocumentAPITest(APITestCase):
    def setUp(self):
        self.bureau = Utilisateur.objects.create_user(
            username="bureau-ai", password="pass", role="bureau_ordre"
        )
        self.dg = Utilisateur.objects.create_user(
            username="dg-ai", password="pass", role="dg"
        )

    @patch("courriers.views.ai.analyser_document")
    def test_bureau_ordre_recoit_des_suggestions(self, analyse):
        analyse.return_value = {
            "objet": "Demande de subvention",
            "categorie": "administratif",
            "priorite": "normal",
        }
        self.client.force_authenticate(self.bureau)
        fichier = SimpleUploadedFile("courrier.pdf", b"contenu", "application/pdf")

        response = self.client.post(
            "/api/courriers/analyser-document/", {"fichier": fichier}, format="multipart"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["suggestions"]["objet"], "Demande de subvention")
        analyse.assert_called_once()

    def test_role_non_autorise_refuse(self):
        self.client.force_authenticate(self.dg)
        fichier = SimpleUploadedFile("courrier.pdf", b"contenu", "application/pdf")

        response = self.client.post(
            "/api/courriers/analyser-document/", {"fichier": fichier}, format="multipart"
        )

        self.assertEqual(response.status_code, 403)

    def test_complete_les_metadonnees_omises_par_le_modele(self):
        suggestions = ai._completer_suggestions(
            {"objet": "Candidature pour le poste de graphiste"},
            """Concordia, le 08/09/2026
Réf. : CAND-2026-047
Objet : Candidature pour le poste de graphiste

Je vous adresse ma candidature pour ce poste.""",
        )

        self.assertEqual(suggestions["numero_source"], "CAND-2026-047")
        self.assertEqual(suggestions["date_source"], "2026-09-08")
        self.assertEqual(suggestions["categorie"], "demande")

    def test_normalise_la_categorie_reponse_avec_accent(self):
        suggestions = ai._valider_suggestions({"categorie": "Réponse"})

        self.assertEqual(suggestions["categorie"], "reponse")


class AnalyseLocaleTest(SimpleTestCase):
    def _reponse_ollama(self, contenu):
        reponse = MagicMock()
        reponse.read.return_value = contenu
        contexte = MagicMock()
        contexte.__enter__.return_value = reponse
        return contexte

    @patch("courriers.ai.urlopen")
    def test_ollama_disponible_retourne_des_suggestions(self, urlopen_mock):
        contenu = json.dumps({
            "message": {"content": json.dumps({"objet": "Demande de stage"})}
        }).encode()
        urlopen_mock.return_value = self._reponse_ollama(contenu)

        self.assertEqual(ai._demander_a_ollama("Texte du courrier"), {"objet": "Demande de stage"})

    @patch("courriers.ai.urlopen", side_effect=URLError("connexion refusée"))
    def test_ollama_indisponible_affiche_une_erreur_claire(self, _urlopen_mock):
        with self.assertRaisesMessage(ai.AnalyseDocumentErreur, "Ollama ne répond pas"):
            ai._demander_a_ollama("Texte du courrier")

    @patch("courriers.ai.urlopen")
    def test_modele_absent_affiche_la_commande_de_telechargement(self, urlopen_mock):
        urlopen_mock.side_effect = HTTPError(
            "http://127.0.0.1:11434/api/chat", 404, "Not Found", None, BytesIO()
        )

        with self.assertRaisesMessage(ai.AnalyseDocumentErreur, "ollama pull qwen2.5:3b"):
            ai._demander_a_ollama("Texte du courrier")

    @patch("courriers.ai.Path.open", new_callable=mock_open)
    @patch("courriers.ai.tempfile.TemporaryDirectory")
    @patch("courriers.ai._extraire_texte", return_value="")
    def test_document_vide_est_refuse(self, _extraire_mock, dossier_mock, _open_mock):
        dossier_mock.return_value.__enter__.return_value = "analyse-temporaire"
        fichier = SimpleUploadedFile("vide.png", b"image", "image/png")

        with self.assertRaisesMessage(ai.AnalyseDocumentErreur, "Aucun texte lisible"):
            ai.analyser_document(fichier)

    @patch("courriers.ai._ocr_image", return_value="Texte reconnu par OCR")
    @patch("courriers.ai._executer", side_effect=["", ""])
    @patch("courriers.ai._commande", side_effect=lambda nom: nom.lower())
    def test_pdf_numerise_est_converti_puis_ocrise(self, _commande, _executer, ocr_mock):
        chemin = Path("analyse-temporaire") / "courrier.pdf"
        page = Path("analyse-temporaire") / "page-1.jpg"
        with patch.object(Path, "glob", return_value=[page]):
            texte = ai._extraire_texte(chemin, ".pdf")

        self.assertEqual(texte, "Texte reconnu par OCR")
        ocr_mock.assert_called_once_with(page)

    @patch("courriers.ai.Path.open", new_callable=mock_open)
    @patch("courriers.ai.tempfile.TemporaryDirectory")
    @patch("courriers.ai._extraire_texte", return_value="   ")
    def test_image_peu_lisible_est_signalee(self, _extraire_mock, dossier_mock, _open_mock):
        dossier_mock.return_value.__enter__.return_value = "analyse-temporaire"
        fichier = SimpleUploadedFile("floue.jpg", b"image", "image/jpeg")

        with self.assertRaisesMessage(ai.AnalyseDocumentErreur, "Aucun texte lisible"):
            ai.analyser_document(fichier)

    @patch("courriers.ai.urlopen")
    def test_json_incorrect_est_refuse(self, urlopen_mock):
        urlopen_mock.return_value = self._reponse_ollama(
            b'{"message": {"content": "ceci n est pas du JSON"}}'
        )

        with self.assertRaisesMessage(ai.AnalyseDocumentErreur, "réponse invalide"):
            ai._demander_a_ollama("Texte du courrier")
