"""Analyse locale des documents de courrier avec Tesseract et Ollama."""

import json
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .models import Courrier


class AnalyseDocumentErreur(Exception):
    """Erreur attendue lors de l'analyse locale d'un document."""


EXTENSIONS_PRIS_EN_CHARGE = {".pdf", ".jpg", ".jpeg", ".png"}
TAILLE_MAX_TEXTE = 12_000


def analyser_document(fichier):
    """Retourne des suggestions validées, sans persister le document ou son texte."""
    extension = Path(fichier.name).suffix.lower()
    if extension not in EXTENSIONS_PRIS_EN_CHARGE:
        raise AnalyseDocumentErreur(
            "L'analyse IA accepte les fichiers PDF, JPG et PNG uniquement."
        )

    with tempfile.TemporaryDirectory(prefix="courrier-ai-") as dossier:
        chemin = Path(dossier) / f"document{extension}"
        with chemin.open("wb") as destination:
            for morceau in fichier.chunks():
                destination.write(morceau)

        texte = _extraire_texte(chemin, extension)

    if not texte.strip():
        raise AnalyseDocumentErreur(
            "Aucun texte lisible n'a été trouvé dans ce document."
        )

    suggestions = _valider_suggestions(_demander_a_ollama(texte[:TAILLE_MAX_TEXTE]))
    # Le modèle local reste la source principale. Ces règles de secours
    # récupèrent toutefois les informations très structurées qu'il pourrait
    # omettre malgré leur présence explicite dans le document OCRisé.
    return _completer_suggestions(suggestions, texte)


def _commande(nom):
    commande = getattr(settings, f"AI_{nom}_COMMAND", "") or nom.lower()
    if not shutil.which(commande):
        raise AnalyseDocumentErreur(
            f"{nom.title()} n'est pas disponible. Installez-le puis définissez "
            f"AI_{nom}_COMMAND si nécessaire."
        )
    return commande


def _executer(commande):
    try:
        return subprocess.run(
            commande,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        ).stdout
    except subprocess.TimeoutExpired as exc:
        raise AnalyseDocumentErreur("L'extraction du document a dépassé 90 secondes.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise AnalyseDocumentErreur(f"Impossible de lire le document. {detail}") from exc


def _ocr_image(chemin):
    return _executer([
        _commande("TESSERACT"), str(chemin), "stdout", "-l", "fra+eng", "--psm", "4"
    ])


def _extraire_texte(chemin, extension):
    if extension != ".pdf":
        return _ocr_image(chemin)

    # Les PDF contenant déjà du texte sont traités directement, sans OCR.
    pdftotext = _commande("PDFTOTEXT")
    texte = _executer([pdftotext, "-layout", str(chemin), "-"])
    if len(texte.strip()) >= 80:
        return texte

    # Pour les PDF scannés, OCR des trois premières pages au maximum.
    pdftoppm = _commande("PDFTOPPM")
    prefixe = chemin.parent / "page"
    _executer([
        pdftoppm, "-f", "1", "-l", "3", "-jpeg", "-r", "200", str(chemin), str(prefixe)
    ])
    pages = sorted(chemin.parent.glob("page-*.jpg"))
    return "\n\n".join(_ocr_image(page) for page in pages)


def _demander_a_ollama(texte):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type_courrier": {"type": "string"},
            "objet": {"type": "string"},
            "numero_source": {"type": "string"},
            "date_source": {"type": "string"},
            "expediteur": {"type": "string"},
            "destinataire": {"type": "string"},
            "categorie": {"type": "string"},
            "priorite": {"type": "string"},
            "date_echeance": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": [
            "type_courrier", "objet", "numero_source", "date_source", "expediteur",
            "destinataire", "categorie", "priorite", "date_echeance", "description",
        ],
    }
    prompt = """Tu extrais des métadonnées d'un courrier administratif français.
Réponds uniquement avec l'objet JSON demandé. Sois extrêmement conservateur :
n'invente aucune information et utilise une chaîne vide lorsqu'elle n'est pas
explicitement lisible. Ignore le texte de remplissage « Lorem ipsum ».
type_courrier: laisse vide sauf si le document indique clairement qu'il est entrant
ou sortant par rapport à l'organisation utilisatrice. Ne déduis pas le type d'après
la seule position des adresses, car l'organisation utilisatrice est inconnue.
objet: recopie l'objet après « Objet : » lorsqu'il existe.
numero_source: cherche en priorité une ligne « Référence », « Réf. »,
« N° », « Numéro » ou « Notre réf. » et recopie sa valeur exacte.
date_source: cherche la date principale du courrier, souvent placée dans
l'en-tête ou introduite par « Fait le » ou « Date ». Convertis-la au format
YYYY-MM-DD. Ne confonds pas cette date avec une date limite ou une échéance.
date_echeance: suggère-la seulement si une date limite est explicitement indiquée.
expediteur et destinataire: recopie les noms/adresses clairement identifiables.
categorie: choisis toujours une seule valeur parmi administratif, juridique,
financier, reponse, demande, notification ou autre. Utilise demande pour une
candidature ou une sollicitation, reponse pour un courrier qui répond à une
demande, financier pour une facture/paiement/budget et juridique pour un
contrat, litige ou texte de loi. Si aucune catégorie ne convient clairement,
renvoie autre.
priorite: urgent ou tres_urgent uniquement si ces mots ou une urgence explicite sont
présents ; sinon normal si une priorité est explicitement indiquée, sinon vide.
description: résumé factuel très court uniquement du contenu réel, jamais une supposition.

DOCUMENT :
""" + texte
    payload = json.dumps({
        "model": settings.AI_OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    requete = Request(
        f"{settings.AI_OLLAMA_URL.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(requete, timeout=settings.AI_OLLAMA_TIMEOUT) as reponse:
            resultat = json.loads(reponse.read().decode("utf-8"))
        return json.loads(resultat["message"]["content"])
    except TimeoutError as exc:
        raise AnalyseDocumentErreur(
            "L'analyse locale prend trop de temps. Réessayez ou augmentez "
            "AI_OLLAMA_TIMEOUT."
        ) from exc
    except HTTPError as exc:
        if exc.code == 404:
            raise AnalyseDocumentErreur(
                "Le modèle Ollama configuré est introuvable. Téléchargez-le avec "
                f"« ollama pull {settings.AI_OLLAMA_MODEL} »."
            ) from exc
        raise AnalyseDocumentErreur(
            f"Ollama a renvoyé une erreur HTTP {exc.code}."
        ) from exc
    except URLError as exc:
        raise AnalyseDocumentErreur(
            "Ollama ne répond pas. Démarrez Ollama et vérifiez AI_OLLAMA_URL."
        ) from exc
    except (KeyError, json.JSONDecodeError) as exc:
        raise AnalyseDocumentErreur("Ollama a renvoyé une réponse invalide.") from exc


def _valider_suggestions(donnees):
    if not isinstance(donnees, dict):
        raise AnalyseDocumentErreur("Les suggestions IA sont invalides.")

    choix = {
        "type_courrier": {valeur for valeur, _ in Courrier.TypeCourrier.choices},
        "categorie": {valeur for valeur, _ in Courrier.Categorie.choices},
        "priorite": {valeur for valeur, _ in Courrier.Priorite.choices},
    }
    resultat = {}
    for champ in (
        "type_courrier", "objet", "numero_source", "date_source", "expediteur",
        "destinataire", "categorie", "priorite", "date_echeance", "description",
    ):
        valeur = donnees.get(champ, "")
        if not isinstance(valeur, str):
            continue
        valeur = valeur.strip()
        if not valeur:
            continue
        if champ == "categorie":
            # Les modèles francophones peuvent naturellement renvoyer
            # « réponse » avec accent, alors que la valeur interne est
            # volontairement stockée sans accent.
            valeur = valeur.lower().replace("é", "e").replace("è", "e")
        if champ in choix and valeur not in choix[champ]:
            continue
        if champ in {"date_source", "date_echeance"}:
            try:
                date.fromisoformat(valeur)
            except ValueError:
                continue
        resultat[champ] = valeur[:2000]
    return resultat


def _completer_suggestions(suggestions, texte):
    """Complète les suggestions IA uniquement à partir d'indices explicites."""
    resultat = dict(suggestions)

    if not resultat.get("numero_source"):
        numero = _extraire_numero_source(texte)
        if numero:
            resultat["numero_source"] = numero

    if not resultat.get("date_source"):
        date_source = _extraire_date_source(texte)
        if date_source:
            resultat["date_source"] = date_source

    if not resultat.get("categorie"):
        resultat["categorie"] = _determiner_categorie(texte)

    return resultat


def _extraire_numero_source(texte):
    """Extrait une référence explicitement libellée sur une ligne du courrier."""
    motif = re.compile(
        r"(?im)^\s*(?:notre\s+)?(?:r[ée]f\.?(?:[ée]rence)?|n[°o]|num[ée]ro)"
        r"\s*[:\-]\s*([^\n]{2,100})$"
    )
    correspondance = motif.search(texte)
    if not correspondance:
        return ""
    return correspondance.group(1).strip(" .;:-")[:100]


def _normaliser_date(jour, mois, annee):
    try:
        return date(int(annee), int(mois), int(jour)).isoformat()
    except ValueError:
        return ""


def _extraire_date_source(texte):
    """Cherche une date de document, en évitant les lignes d'échéance."""
    motifs = (
        r"(?im)^\s*(?:fait\s+[àa].*?\s+le|date)\s*[:\-]?\s*"
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        r"(?im)^.*?\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
    )
    for motif in motifs:
        for correspondance in re.finditer(motif, texte):
            ligne = correspondance.group(0).lower()
            if "échéance" in ligne or "echeance" in ligne or "limite" in ligne:
                continue
            resultat = _normaliser_date(*correspondance.groups())
            if resultat:
                return resultat
    return ""


def _determiner_categorie(texte):
    """Classe le document dans une catégorie métier, avec « autre » par défaut."""
    contenu = texte.lower()
    categories = (
        ("juridique", ("juridique", "tribunal", "litige", "avocat", "contrat", "loi")),
        ("financier", ("facture", "paiement", "budget", "financ", "comptabil", "devis", "règlement")),
        ("notification", ("notification", "communiqué", "avis de")),
        ("reponse", ("en réponse", "en reponse", "suite à votre demande")),
        ("demande", ("demande", "sollicitation", "candidature", "postule")),
        ("administratif", ("administratif", "administration", "dossier administratif")),
    )
    for categorie, mots_cles in categories:
        if any(mot in contenu for mot in mots_cles):
            return categorie
    return "autre"
