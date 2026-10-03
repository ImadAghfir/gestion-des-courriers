import { useEffect, useMemo, useState } from "react";
import illustrationConnexion from "./assets/interff.webp";

const API_URL = "/api";

const libellesStatut = {
  enregistre: "Enregistré",
  affect_provisoire: "Affect. provisoire",
  transmis: "Transmis au DG",
  valide: "Validé",
  rejete: "Rejeté",
  affecte: "Affecté",
  retourne_dg: "Retourné au DG",
  en_traitement: "En traitement",
  traite: "Traité",
  archive: "Archivé",
  envoye: "Envoyé",
};

const libellesRole = {
  admin: "Administrateur",
  bureau_ordre: "Bureau d'Ordre",
  dg: "Directeur Général",
  secretaire: "Secrétaire",
  chef_departement: "Chef de Département",
  chef_service: "Chef de Service",
};

const libellesPriorite = {
  normal: "Normal",
  urgent: "Urgent",
  tres_urgent: "Très urgent",
};

const champsSuggestionsIA = [
  ["type_courrier", "Type de courrier"],
  ["numero_source", "Numéro source"],
  ["date_source", "Date source"],
  ["categorie", "Catégorie"],
  ["objet", "Objet"],
  ["expediteur", "Expéditeur"],
  ["destinataire", "Destinataire"],
  ["priorite", "Priorité"],
  ["date_echeance", "Date d’échéance"],
  ["description", "Résumé"],
];

const filtresVides = {
  q: "",
  statut: "",
  priorite: "",
  type_courrier: "",
  categorie: "",
  departement: "",
  service: "",
  reception_du: "",
  reception_au: "",
  avec_instructions: "",
};

const formulaireVide = {
  type_courrier: "entrant",
  objet: "",
  numero_source: "",
  date_source: "",
  date_reception: "",
  expediteur: "",
  destinataire: "",
  categorie: "administratif",
  priorite: "normal",
  date_echeance: "",
  description: "",
  affectations_provisoires: [],
};

function formaterDate(valeur) {
  if (!valeur) return "—";
  const date = new Date(valeur);
  if (Number.isNaN(date.getTime())) return valeur;
  return date.toLocaleDateString("fr-FR");
}

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [afficherMotDePasse, setAfficherMotDePasse] = useState(false);
  const [seSouvenir, setSeSouvenir] = useState(true);
  const [token, setToken] = useState("");
  const [profil, setProfil] = useState(null);
  const [courriers, setCourriers] = useState([]);
  const [notifications, setNotifications] = useState([]);
  // Compteur renvoyé par le serveur : exact même si la liste affichée est
  // limitée aux notifications les plus récentes.
  const [compteurNotifications, setCompteurNotifications] = useState({
    non_lues: 0,
    total: 0,
  });
  const [departements, setDepartements] = useState([]);
  const [services, setServices] = useState([]);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [chargement, setChargement] = useState(false);
  const [route, setRoute] = useState(() => {
    const hash = window.location.hash.replace(/^#\/?/, "");
    return hash ? "/" + hash.replace(/^\//, "") : "/courriers";
  });
  const [afficherNotifications, setAfficherNotifications] = useState(false);
  const [formulaire, setFormulaire] = useState(formulaireVide);
  const [documentNumerise, setDocumentNumerise] = useState(null);
  const [analyseEnCours, setAnalyseEnCours] = useState(false);
  const [suggestionsIA, setSuggestionsIA] = useState(null);
  const [courrierDetail, setCourrierDetail] = useState(null);
  // Panneau d'action contextuel : { courrier, type } où type ∈
  // "rejeter" | "affectation-finale" | "retourner-dg" | "affecter-service"
  // | "instructions-dg" | "instructions-dept" | "commenter"
  const [panneauAction, setPanneauAction] = useState(null);
  const [champsAction, setChampsAction] = useState({});
  const [filtres, setFiltres] = useState(filtresVides);
  const [statistiques, setStatistiques] = useState(null);
  const [journal, setJournal] = useState(null);
  const [actionsJournal, setActionsJournal] = useState([]);
  const [utilisateurs, setUtilisateurs] = useState([]);
  const [ongletAdmin, setOngletAdmin] = useState("utilisateurs");
  const [donneesAdmin, setDonneesAdmin] = useState({
    utilisateurs: [],
    departements: [],
    services: [],
  });
  const [formulaireAdmin, setFormulaireAdmin] = useState(null);
  const [filtresJournal, setFiltresJournal] = useState({
    q: "",
    action: "",
    utilisateur: "",
    du: "",
    au: "",
    page: 1,
  });
  const [motsDePasse, setMotsDePasse] = useState({
    ancien: "",
    nouveau: "",
    confirmation: "",
  });

  const role = profil?.role || "";

  // ------------------------------------------------------------------
  // Appels API
  // ------------------------------------------------------------------

  async function apiFetch(url, options = {}, accessToken) {
    const tok = accessToken || token;
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    if (tok) headers["Authorization"] = `Bearer ${tok}`;

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
      localStorage.removeItem("access_token");
      sessionStorage.removeItem("access_token");
      setToken("");
      setProfil(null);
      setCourriers([]);
      setUsername("");
      throw new Error("Session expirée. Veuillez vous reconnecter.");
    }
    return response;
  }

  function construireRecherche(filtresActifs) {
    const parametres = new URLSearchParams();
    Object.entries(filtresActifs).forEach(([cle, valeur]) => {
      if (valeur) parametres.set(cle, valeur);
    });
    const chaine = parametres.toString();
    return chaine ? `?${chaine}` : "";
  }

  async function chargerCourriers(accessToken, filtresActifs) {
    setChargement(true);
    setErreur("");

    try {
      const response = await apiFetch(
        `${API_URL}/courriers/${construireRecherche(filtresActifs ?? filtres)}`,
        {},
        accessToken
      );

      if (!response.ok) throw new Error("Impossible de charger les courriers.");
      setCourriers(await response.json());
    } catch (error) {
      setErreur(error.message);
    } finally {
      setChargement(false);
    }
  }

  async function chargerDonnees(accessToken, filtresActifs) {
    setErreur("");

    try {
      const [notificationsRep, compteurRep, departementsRep, servicesRep] = await Promise.all([
        apiFetch(`${API_URL}/notifications/`, {}, accessToken),
        apiFetch(`${API_URL}/notifications/compteur/`, {}, accessToken),
        apiFetch(`${API_URL}/departements/`, {}, accessToken),
        apiFetch(`${API_URL}/services/`, {}, accessToken),
      ]);

      if (notificationsRep.ok) setNotifications(await notificationsRep.json());
      if (compteurRep.ok) setCompteurNotifications(await compteurRep.json());
      if (departementsRep.ok) setDepartements(await departementsRep.json());
      if (servicesRep.ok) setServices(await servicesRep.json());
    } catch (error) {
      setErreur(error.message);
    }

    await chargerCourriers(accessToken, filtresActifs);
  }

  async function chargerProfil(accessToken) {
    const response = await apiFetch(`${API_URL}/auth/me/`, {}, accessToken);
    if (response.ok) {
      const donnees = await response.json();
      setProfil(donnees);
      return donnees;
    }
    return null;
  }

  async function seConnecter(event) {
    event.preventDefault();
    setErreur("");
    setChargement(true);

    try {
      const response = await fetch(`${API_URL}/auth/login/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const donnees = await response.json();

      if (!response.ok) {
        throw new Error(
          donnees.detail || "Nom d'utilisateur ou mot de passe incorrect."
        );
      }

      const stockage = seSouvenir ? localStorage : sessionStorage;
      stockage.setItem("access_token", donnees.access);
      setToken(donnees.access);
      await chargerProfil(donnees.access);
      setPassword("");
      await chargerDonnees(donnees.access);
    } catch (error) {
      setErreur(error.message);
      setChargement(false);
    }
  }

  function seDeconnecter() {
    localStorage.removeItem("access_token");
    sessionStorage.removeItem("access_token");
    setToken("");
    setProfil(null);
    setCourriers([]);
    setUsername("");
    setMessage("");
    setNotifications([]);
    setAfficherNotifications(false);
    setCourrierDetail(null);
    setPanneauAction(null);
    setStatistiques(null);
    setJournal(null);
    window.location.hash = "#/courriers";
  }

  useEffect(() => {
    function synchroniserRoute() {
      const hash = window.location.hash.replace(/^#\/?/, "");
      const chemin = hash ? "/" + hash.replace(/^\//, "") : "/courriers";
      setRoute(chemin);
    }
    window.addEventListener("hashchange", synchroniserRoute);
    return () => window.removeEventListener("hashchange", synchroniserRoute);
  }, []);

  useEffect(() => {
    const tokenSauvegarde =
      localStorage.getItem("access_token") ||
      sessionStorage.getItem("access_token");

    if (!tokenSauvegarde) return;

    async function restaurerSession() {
      try {
        const profilResponse = await fetch(`${API_URL}/auth/me/`, {
          headers: { Authorization: `Bearer ${tokenSauvegarde}` },
        });

        if (!profilResponse.ok) {
          localStorage.removeItem("access_token");
          sessionStorage.removeItem("access_token");
          return;
        }

        setToken(tokenSauvegarde);
        setProfil(await profilResponse.json());
        await chargerDonnees(tokenSauvegarde);
      } catch (error) {
        localStorage.removeItem("access_token");
        sessionStorage.removeItem("access_token");
        setErreur(error.message);
      }
    }

    restaurerSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------------------
  // Effet « ripple » au clic sur les boutons
  // ------------------------------------------------------------------

  useEffect(() => {
    function creerOndulation(event) {
      const bouton = event.target.closest("button");
      if (!bouton || bouton.disabled) return;
      // Pas d'ondulation sur les boutons transparents (liens, afficher/masquer)
      if (
        bouton.classList.contains("lien-courrier") ||
        bouton.classList.contains("basculer-mot-de-passe")
      ) {
        return;
      }

      const rectangle = bouton.getBoundingClientRect();
      const diametre = Math.max(rectangle.width, rectangle.height) * 2;

      const onde = document.createElement("span");
      onde.className = "onde-ripple";
      onde.style.width = `${diametre}px`;
      onde.style.height = `${diametre}px`;
      onde.style.left = `${event.clientX - rectangle.left - diametre / 2}px`;
      onde.style.top = `${event.clientY - rectangle.top - diametre / 2}px`;

      bouton.appendChild(onde);
      onde.addEventListener("animationend", () => onde.remove());
    }

    document.addEventListener("pointerdown", creerOndulation);
    return () => document.removeEventListener("pointerdown", creerOndulation);
  }, []);

  // ------------------------------------------------------------------
  // Déconnexion automatique après 30 minutes d'inactivité (§10.1)
  // ------------------------------------------------------------------

  useEffect(() => {
    if (!token) return undefined;

    const DELAI_INACTIVITE = 30 * 60 * 1000; // 30 minutes
    let minuteur;

    function deconnexionInactivite() {
      seDeconnecter();
      setErreur(
        "Vous avez été déconnecté après 30 minutes d'inactivité. " +
          "Veuillez vous reconnecter."
      );
    }

    function reinitialiserMinuteur() {
      clearTimeout(minuteur);
      minuteur = setTimeout(deconnexionInactivite, DELAI_INACTIVITE);
    }

    const evenements = ["mousedown", "keydown", "scroll", "touchstart"];
    evenements.forEach((evenement) =>
      window.addEventListener(evenement, reinitialiserMinuteur)
    );
    reinitialiserMinuteur();

    return () => {
      clearTimeout(minuteur);
      evenements.forEach((evenement) =>
        window.removeEventListener(evenement, reinitialiserMinuteur)
      );
    };
     
  }, [token]);

  // ------------------------------------------------------------------
  // Changement de mot de passe (première connexion, §10.1)
  // ------------------------------------------------------------------

  async function changerMotDePasse(event) {
    event.preventDefault();
    setErreur("");
    setMessage("");

    if (motsDePasse.nouveau !== motsDePasse.confirmation) {
      setErreur("Le nouveau mot de passe et sa confirmation ne correspondent pas.");
      return;
    }

    try {
      const response = await apiFetch(`${API_URL}/auth/changer-mot-de-passe/`, {
        method: "POST",
        body: JSON.stringify({
          ancien_mot_de_passe: motsDePasse.ancien,
          nouveau_mot_de_passe: motsDePasse.nouveau,
        }),
      });

      const resultat = await response.json();

      if (!response.ok) {
        throw new Error(resultat.detail || "Changement de mot de passe impossible.");
      }

      setMotsDePasse({ ancien: "", nouveau: "", confirmation: "" });
      setProfil({ ...profil, doit_changer_mot_de_passe: false });
      setMessage("Mot de passe modifié avec succès. Bienvenue !");
    } catch (error) {
      setErreur(error.message);
    }
  }

  // ------------------------------------------------------------------
  // Actions du workflow
  // ------------------------------------------------------------------

  async function executerAction(courrierId, action, corps, texteSucces) {
    setErreur("");
    setMessage("");

    try {
      const response = await apiFetch(
        `${API_URL}/courriers/${courrierId}/${action}/`,
        { method: "POST", body: corps ? JSON.stringify(corps) : undefined }
      );

      const resultat = await response.json();

      if (!response.ok) {
        throw new Error(resultat.detail || "Action impossible.");
      }

      setMessage(texteSucces);
      setPanneauAction(null);
      setChampsAction({});
      setCourrierDetail(null);
      await chargerDonnees(token);
    } catch (error) {
      setErreur(error.message);
    }
  }

  async function chargerStatistiques() {
    setErreur("");
    try {
      const response = await apiFetch(`${API_URL}/statistiques/`);
      const donnees = await response.json();

      if (!response.ok) {
        throw new Error(donnees.detail || "Impossible de charger les statistiques.");
      }

      setStatistiques(donnees);
      return donnees;
    } catch (error) {
      setErreur(error.message);
      return null;
    }
  }

  // ------------------------------------------------------------------
  // Journal d'activité (Administrateur, §4.2)
  // ------------------------------------------------------------------

  async function chargerJournal(filtresActifs) {
    const actifs = filtresActifs ?? filtresJournal;
    setErreur("");

    try {
      const parametres = new URLSearchParams();
      Object.entries(actifs).forEach(([cle, valeur]) => {
        if (valeur && !(cle === "page" && valeur === 1)) {
          parametres.set(cle, valeur);
        }
      });

      const response = await apiFetch(
        `${API_URL}/journal/${parametres.toString() ? `?${parametres}` : ""}`
      );
      const donnees = await response.json();

      if (!response.ok) {
        throw new Error(donnees.detail || "Impossible de charger le journal.");
      }

      setJournal(donnees);

      if (actionsJournal.length === 0) {
        const reponseActions = await apiFetch(`${API_URL}/journal/actions/`);
        if (reponseActions.ok) setActionsJournal(await reponseActions.json());
      }

      if (utilisateurs.length === 0) {
        const reponseUtilisateurs = await apiFetch(`${API_URL}/utilisateurs/`);
        if (reponseUtilisateurs.ok) setUtilisateurs(await reponseUtilisateurs.json());
      }

      return donnees;
    } catch (error) {
      setErreur(error.message);
      return null;
    }
  }

  function changerPageJournal(delta) {
    const suivant = { ...filtresJournal, page: filtresJournal.page + delta };
    setFiltresJournal(suivant);
    chargerJournal(suivant);
  }

  // ------------------------------------------------------------------
  // Administration : utilisateurs, départements, services (§5.11, §5.12)
  // ------------------------------------------------------------------

  async function chargerDonneesAdmin() {
    try {
      const [rUtilisateurs, rDepartements, rServices] = await Promise.all([
        apiFetch(`${API_URL}/utilisateurs/?tous=1`),
        apiFetch(`${API_URL}/departements/?tous=1`),
        apiFetch(`${API_URL}/services/?tous=1`),
      ]);

      if (!rUtilisateurs.ok) {
        throw new Error("Accès à l'administration refusé.");
      }

      const donnees = {
        utilisateurs: await rUtilisateurs.json(),
        departements: rDepartements.ok ? await rDepartements.json() : [],
        services: rServices.ok ? await rServices.json() : [],
      };
      setDonneesAdmin(donnees);
      return donnees;
    } catch (error) {
      setErreur(error.message);
      return null;
    }
  }

  // Chargement automatique des données selon l'URL de la page active
  useEffect(() => {
    if (!token) return;

    // Defer stateful loading so this effect only initiates async work.
    void Promise.resolve().then(() => {
      if (route === "/statistiques") {
        return chargerStatistiques();
      }

      if (route.startsWith("/administration")) {
        const parties = route.split("/");
        if (parties[2] && ["utilisateurs", "departements", "services"].includes(parties[2])) {
          setOngletAdmin(parties[2]);
        }
        return chargerDonneesAdmin();
      }

      if (route === "/journal") return chargerJournal();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route, token]);

  function ouvrirFormulaireAdmin(type, element) {
    setErreur("");
    setMessage("");
    setFormulaireAdmin({
      type,
      id: element?.id ?? null,
      valeurs: element
        ? { ...element, mot_de_passe: "" }
        : type === "utilisateurs"
          ? {
              username: "", first_name: "", last_name: "", email: "",
              role: "", departement: "", service: "", mot_de_passe: "",
            }
          : type === "departements"
            ? { nom: "", code: "", description: "" }
            : { nom: "", code: "", departement: "", description: "" },
    });
  }

  async function enregistrerElementAdmin(event) {
    event.preventDefault();
    setErreur("");
    setMessage("");

    const { type, id, valeurs } = formulaireAdmin;
    const corps = { ...valeurs };

    // Nettoyage : champs vides → null / absents
    ["departement", "service", "responsable"].forEach((champ) => {
      if (champ in corps) corps[champ] = corps[champ] ? Number(corps[champ]) : null;
    });
    if (!corps.mot_de_passe) delete corps.mot_de_passe;
    ["role_label", "departement_nom", "service_nom", "responsable_nom",
      "nom_complet", "nombre_services", "doit_changer_mot_de_passe",
      "is_active", "statut", "id"].forEach((champ) => delete corps[champ]);

    try {
      const response = await apiFetch(
        `${API_URL}/${type}/${id ? `${id}/` : ""}`,
        { method: id ? "PATCH" : "POST", body: JSON.stringify(corps) }
      );
      const resultat = await response.json();

      if (!response.ok) {
        const details = Object.entries(resultat)
          .map(([champ, messages]) => `${champ} : ${[].concat(messages).join(" ")}`)
          .join(" | ");
        throw new Error(details || "Enregistrement impossible.");
      }

      setMessage(id ? "Modification enregistrée." : "Création effectuée avec succès.");
      setFormulaireAdmin(null);
      await chargerDonneesAdmin();
      await chargerDonnees(token);
    } catch (error) {
      setErreur(error.message);
    }
  }

  async function basculerStatutAdmin(type, element) {
    setErreur("");
    setMessage("");

    try {
      const response = await apiFetch(
        `${API_URL}/${type}/${element.id}/changer-statut/`,
        { method: "POST" }
      );
      const resultat = await response.json();

      if (!response.ok) {
        throw new Error(resultat.detail || "Opération impossible.");
      }

      setMessage(
        (resultat.is_active ?? resultat.statut === "actif")
          ? "Élément réactivé."
          : "Élément désactivé (les données sont conservées)."
      );
      await chargerDonneesAdmin();
      await chargerDonnees(token);
    } catch (error) {
      setErreur(error.message);
    }
  }

  async function marquerNotificationLue(notificationId) {
    try {
      const response = await apiFetch(
        `${API_URL}/notifications/${notificationId}/marquer_lue/`,
        { method: "POST" }
      );

      if (!response.ok) {
        throw new Error("Impossible de marquer la notification comme lue.");
      }

      const notificationMiseAJour = await response.json();
      setNotifications((liste) =>
        liste.map((notification) =>
          notification.id === notificationMiseAJour.id
            ? notificationMiseAJour
            : notification
        )
      );
      setCompteurNotifications((compteur) => ({
        ...compteur,
        non_lues: Math.max(0, compteur.non_lues - 1),
      }));
    } catch (error) {
      setErreur(error.message);
    }
  }

  async function toutMarquerLues() {
    setErreur("");
    try {
      const response = await apiFetch(
        `${API_URL}/notifications/tout-marquer-lues/`,
        { method: "POST" }
      );
      const resultat = await response.json();

      if (!response.ok) {
        throw new Error(resultat.detail || "Opération impossible.");
      }

      setMessage(resultat.detail);
      await chargerDonnees(token);
    } catch (error) {
      setErreur(error.message);
    }
  }

  // ------------------------------------------------------------------
  // Enregistrement d'un courrier (Bureau d'Ordre)
  // ------------------------------------------------------------------

  function modifierFormulaire(event) {
    const { name, value } = event.target;
    setFormulaire((precedent) => {
      const suivant = { ...precedent, [name]: value };
      if (name === "type_courrier") {
        suivant.categorie = value === "entrant" ? "administratif" : "reponse";
        suivant.affectations_provisoires = [];
      }
      return suivant;
    });
  }

  // Formats et taille acceptés (cahier des charges §5.8)
  const FORMATS_DOCUMENT = ".pdf,.doc,.docx,.jpg,.jpeg,.png";
  const TAILLE_MAX_DOCUMENT = 10 * 1024 * 1024; // 10 Mo

  function verifierDocument(fichier) {
    if (!fichier) return null;
    if (fichier.size > TAILLE_MAX_DOCUMENT) {
      return "Le document dépasse la taille maximale autorisée (10 Mo).";
    }
    const extension = fichier.name.split(".").pop().toLowerCase();
    if (!["pdf", "doc", "docx", "jpg", "jpeg", "png"].includes(extension)) {
      return "Format non accepté. Formats autorisés : PDF, Word, JPG, PNG.";
    }
    return null;
  }

  /** Téléverse un document numérisé sur un courrier (multipart/form-data). */
  async function televerserDocument(courrierId, fichier) {
    const donnees = new FormData();
    donnees.append("fichier", fichier);

    // Pas d'en-tête Content-Type : le navigateur ajoute la frontière multipart.
    const response = await fetch(
      `${API_URL}/courriers/${courrierId}/ajouter_document/`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: donnees,
      }
    );

    if (!response.ok) {
      const resultat = await response.json().catch(() => ({}));
      throw new Error(resultat.detail || "Échec de l'envoi du document.");
    }

    return response.json();
  }

  async function joindreDocumentAuCourrier(courrier, fichier) {
    const probleme = verifierDocument(fichier);
    if (probleme) {
      setErreur(probleme);
      return;
    }

    setErreur("");
    setMessage("");

    try {
      const courrierMisAJour = await televerserDocument(courrier.id, fichier);
      setMessage(`Document « ${fichier.name} » joint au courrier ${courrier.numero}.`);
      setCourrierDetail(courrierMisAJour);
      await chargerDonnees(token);
    } catch (error) {
      setErreur(error.message);
    }
  }

  async function analyserDocument() {
    const probleme = verifierDocument(documentNumerise);
    if (probleme) {
      setErreur(probleme);
      return;
    }

    setAnalyseEnCours(true);
    setErreur("");
    setMessage("");
    setSuggestionsIA(null);
    const donnees = new FormData();
    donnees.append("fichier", documentNumerise);

    try {
      const response = await fetch(`${API_URL}/courriers/analyser-document/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: donnees,
      });
      const resultat = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(resultat.detail || "Analyse du document impossible.");
      }

      const suggestions = resultat.suggestions || {};
      setFormulaire((precedent) => ({ ...precedent, ...suggestions }));
      setSuggestionsIA(suggestions);
      setMessage(resultat.detail);
    } catch (error) {
      setErreur(error.message);
    } finally {
      setAnalyseEnCours(false);
    }
  }

  async function enregistrerCourrier(event) {
    event.preventDefault();
    setErreur("");
    setMessage("");

    const probleme = verifierDocument(documentNumerise);
    if (probleme) {
      setErreur(probleme);
      return;
    }

    const donnees = {
      type_courrier: formulaire.type_courrier,
      objet: formulaire.objet,
      numero_source: formulaire.numero_source,
      date_source: formulaire.date_source,
      categorie: formulaire.categorie,
      priorite: formulaire.priorite,
      description: formulaire.description,
    };

    if (formulaire.type_courrier === "entrant") {
      donnees.date_reception = formulaire.date_reception;
      donnees.expediteur = formulaire.expediteur;
      if (formulaire.affectations_provisoires.length) {
        donnees.affectations_provisoires = formulaire.affectations_provisoires.map(Number);
      }
    } else {
      donnees.destinataire = formulaire.destinataire;
    }

    if (formulaire.date_echeance) donnees.date_echeance = formulaire.date_echeance;

    try {
      const response = await apiFetch(`${API_URL}/courriers/`, {
        method: "POST",
        body: JSON.stringify(donnees),
      });

      const resultat = await response.json();

      if (!response.ok) {
        const details = Object.entries(resultat)
          .map(([champ, messages]) => `${champ} : ${[].concat(messages).join(" ")}`)
          .join(" | ");
        throw new Error(details || "Enregistrement impossible.");
      }

      let complement = "";
      if (documentNumerise) {
        try {
          await televerserDocument(resultat.id, documentNumerise);
          complement = ` Document « ${documentNumerise.name} » joint.`;
        } catch (erreurDocument) {
          complement = ` Attention : le document n'a pas pu être joint (${erreurDocument.message}). Vous pouvez le joindre depuis la fiche du courrier.`;
        }
      }

      setMessage(`Courrier ${resultat.numero} enregistré avec succès.${complement}`);
      setFormulaire(formulaireVide);
      setDocumentNumerise(null);
      setSuggestionsIA(null);
      window.location.hash = "#/courriers";
      await chargerDonnees(token);
    } catch (error) {
      setErreur(error.message);
    }
  }

  function annulerEnregistrement(event) {
    event.preventDefault();
    setFormulaire({ ...formulaireVide });
    setDocumentNumerise(null);
    setSuggestionsIA(null);
    setAnalyseEnCours(false);
    setErreur("");
    setMessage("");
    const champFichier = document.getElementById("document_numerise");
    if (champFichier) champFichier.value = "";
    window.location.hash = "#/courriers";
  }

  // ------------------------------------------------------------------
  // Tableau de bord par rôle (§5.2)
  // ------------------------------------------------------------------

  const indicateurs = useMemo(() => {
    const aujourdHui = new Date().toISOString().slice(0, 10);
    const moisCourant = aujourdHui.slice(0, 7);
    const enRetard = (courrier) =>
      courrier.date_echeance &&
      courrier.date_echeance < aujourdHui &&
      !["traite", "archive"].includes(courrier.statut);
    const urgents = courriers.filter(
      (courrier) =>
        ["urgent", "tres_urgent"].includes(courrier.priorite) &&
        !["traite", "archive"].includes(courrier.statut)
    ).length;

    if (role === "bureau_ordre") {
      return [
        ["Enregistrés aujourd'hui", courriers.filter((c) => c.date_creation?.slice(0, 10) === aujourdHui).length],
        ["Avec affectation provisoire", courriers.filter((c) => c.affectations_provisoires?.length).length],
        ["En attente de transmission", courriers.filter((c) => ["enregistre", "affect_provisoire", "rejete"].includes(c.statut)).length],
        ["À archiver", courriers.filter((c) => c.statut === "traite" || (c.type_courrier === "sortant" && c.statut === "envoye")).length],
        ["Urgents", urgents],
      ];
    }
    if (role === "dg" || role === "secretaire" || role === "admin") {
      const traites = courriers.filter((c) => ["traite", "archive"].includes(c.statut)).length;
      return [
        ["En attente de validation", courriers.filter((c) => c.statut === "transmis").length],
        ["Provisoires à confirmer", courriers.filter((c) => c.statut === "transmis" && c.affectations_provisoires?.length).length],
        ["Retours à réaffecter", courriers.filter((c) => c.statut === "retourne_dg").length],
        ["Urgents", urgents],
        ["Taux de traitement", `${Math.round((traites / Math.max(courriers.length, 1)) * 100)} %`],
        ["En retard", courriers.filter(enRetard).length],
      ];
    }
    if (role === "chef_departement") {
      return [
        ["Courriers de mon département", courriers.length],
        ["Instructions du DG", courriers.filter((c) => c.instructions_dg).length],
        ["À affecter à un service", courriers.filter((c) => c.statut === "affecte" && !c.service).length],
        ["En cours", courriers.filter((c) => c.statut === "en_traitement").length],
        ["En retard", courriers.filter(enRetard).length],
      ];
    }
    if (role === "chef_service") {
      return [
        ["À traiter", courriers.filter((c) => c.statut === "affecte").length],
        ["Avec instructions", courriers.filter((c) => c.instructions_chef_dept).length],
        ["En cours", courriers.filter((c) => c.statut === "en_traitement").length],
        ["Traités ce mois", courriers.filter((c) => ["traite", "archive"].includes(c.statut) && c.date_creation?.slice(0, 7) === moisCourant).length],
        ["Urgents", urgents],
      ];
    }
    return [];
  }, [courriers, role]);

  // ------------------------------------------------------------------
  // Actions disponibles par rôle et par statut
  // ------------------------------------------------------------------

  function ouvrirPanneau(courrier, type) {
    setPanneauAction({ courrier, type });
    setChampsAction({});
    setErreur("");
    setMessage("");
  }

  function actionsPour(courrier) {
    const boutons = [];
    const estEntrant = courrier.type_courrier === "entrant";

    if (role === "bureau_ordre" || role === "admin") {
      if (estEntrant && ["enregistre", "affect_provisoire", "rejete"].includes(courrier.statut)) {
        boutons.push(
          <button
            key="transmettre"
            className="petit-bouton"
            onClick={() =>
              executerAction(courrier.id, "transmettre", null, "Courrier transmis au DG.")
            }
          >
            Transmettre au DG
          </button>
        );
      }
      if (!estEntrant && courrier.statut === "valide") {
        boutons.push(
          <button
            key="envoyer"
            className="petit-bouton"
            onClick={() =>
              executerAction(courrier.id, "envoyer", null, "Courrier marqué comme envoyé.")
            }
          >
            Marquer envoyé
          </button>
        );
      }
      if (
        (estEntrant && courrier.statut === "traite") ||
        (!estEntrant && courrier.statut === "envoye")
      ) {
        boutons.push(
          <button
            key="archiver"
            className="petit-bouton"
            onClick={() =>
              executerAction(courrier.id, "archiver", null, "Courrier archivé.")
            }
          >
            Archiver
          </button>
        );
      }
    }

    if (role === "dg" || role === "secretaire" || role === "admin") {
      if (
        (estEntrant && courrier.statut === "transmis") ||
        (!estEntrant && courrier.statut === "enregistre")
      ) {
        boutons.push(
          <button
            key="valider"
            className="petit-bouton"
            onClick={() =>
              executerAction(courrier.id, "valider", null, "Courrier validé.")
            }
          >
            Valider
          </button>,
          <button
            key="rejeter"
            className="petit-bouton bouton-danger"
            onClick={() => ouvrirPanneau(courrier, "rejeter")}
          >
            Rejeter
          </button>
        );
      }
      if (estEntrant && ["valide", "retourne_dg"].includes(courrier.statut)) {
        boutons.push(
          <button
            key="affectation-finale"
            className="petit-bouton"
            onClick={() => ouvrirPanneau(courrier, "affectation-finale")}
          >
            {courrier.statut === "retourne_dg" ? "Réaffecter" : "Affectation finale"}
          </button>
        );
      }
      if (
        estEntrant &&
        courrier.statut === "affecte" &&
        (role === "dg" || role === "secretaire") &&
        !courrier.service
      ) {
        boutons.push(
          <button
            key="instructions-dg"
            className="petit-bouton"
            onClick={() => ouvrirPanneau(courrier, "instructions-dg")}
          >
            Instructions
          </button>
        );
      }
    }

    if (role === "chef_departement") {
      if (courrier.statut === "affecte" && !courrier.service) {
        boutons.push(
          <button
            key="affecter-service"
            className="petit-bouton"
            onClick={() => ouvrirPanneau(courrier, "affecter-service")}
          >
            Affecter à un service
          </button>,
          <button
            key="retourner-dg"
            className="petit-bouton bouton-danger"
            onClick={() => ouvrirPanneau(courrier, "retourner-dg")}
          >
            Retourner au DG
          </button>
        );
      }
      if (["affecte", "en_traitement"].includes(courrier.statut) && courrier.service) {
        boutons.push(
          <button
            key="instructions-dept"
            className="petit-bouton"
            onClick={() => ouvrirPanneau(courrier, "instructions-dept")}
          >
            Instructions
          </button>
        );
      }
    }

    if (role === "chef_service") {
      if (courrier.statut === "affecte" && courrier.service) {
        boutons.push(
          <button
            key="traiter"
            className="petit-bouton"
            onClick={() =>
              executerAction(courrier.id, "traiter", null, "Traitement démarré.")
            }
          >
            Traiter
          </button>
        );
      }
      if (courrier.statut === "en_traitement") {
        boutons.push(
          <button
            key="cloturer"
            className="petit-bouton"
            onClick={() =>
              executerAction(courrier.id, "cloturer", null, "Courrier clôturé (traité).")
            }
          >
            Clôturer
          </button>
        );
      }
    }

    boutons.push(
      <button
        key="details"
        className="petit-bouton bouton-discret"
        onClick={() => {
          setCourrierDetail(courrier);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      >
        Détails
      </button>
    );

    if (courrier.statut !== "archive") {
      boutons.push(
        <button
          key="commenter"
          className="petit-bouton bouton-discret"
          onClick={() => ouvrirPanneau(courrier, "commenter")}
        >
          Commenter
        </button>
      );
    }

    return boutons;
  }

  // ------------------------------------------------------------------
  // Rendu du panneau d'action contextuel
  // ------------------------------------------------------------------

  function rendrePanneauAction() {
    if (!panneauAction) return null;
    const { courrier, type } = panneauAction;

    const configuration = {
      rejeter: {
        titre: `Rejeter ${courrier.numero}`,
        champs: [["commentaire", "Motif du rejet (obligatoire)", "textarea"]],
        envoyer: () =>
          executerAction(
            courrier.id, "rejeter",
            { commentaire: champsAction.commentaire || "" },
            "Courrier rejeté."
          ),
      },
      "affectation-finale": {
        titre:
          courrier.statut === "retourne_dg"
            ? `Réaffecter ${courrier.numero}`
            : `Affectation finale — ${courrier.numero}`,
        champs: [
          ["departement_id", "Département officiel", "departement"],
          ["instructions", "Instructions au Chef de Département (optionnel)", "textarea"],
        ],
        envoyer: () =>
          executerAction(
            courrier.id, "affectation-finale",
            {
              departement_id: Number(champsAction.departement_id || 0),
              instructions: champsAction.instructions || "",
            },
            "Affectation finale effectuée."
          ),
      },
      "retourner-dg": {
        titre: `Retourner ${courrier.numero} au DG`,
        champs: [["commentaire", "Commentaire (obligatoire)", "textarea"]],
        envoyer: () =>
          executerAction(
            courrier.id, "retourner-dg",
            { commentaire: champsAction.commentaire || "" },
            "Courrier retourné au DG."
          ),
      },
      "affecter-service": {
        titre: `Affecter ${courrier.numero} à un service`,
        champs: [
          ["service_id", "Service de mon département", "service"],
          ["instructions", "Instructions au Chef de Service (optionnel)", "textarea"],
        ],
        envoyer: () =>
          executerAction(
            courrier.id, "affecter-service",
            {
              service_id: Number(champsAction.service_id || 0),
              instructions: champsAction.instructions || "",
            },
            "Courrier affecté au service."
          ),
      },
      "instructions-dg": {
        titre: `Instructions du DG — ${courrier.numero}`,
        champs: [["instructions", "Instructions", "textarea"]],
        envoyer: () =>
          executerAction(
            courrier.id, "instructions-dg",
            { instructions: champsAction.instructions || "" },
            "Instructions enregistrées."
          ),
      },
      "instructions-dept": {
        titre: `Instructions au Chef de Service — ${courrier.numero}`,
        champs: [["instructions", "Instructions", "textarea"]],
        envoyer: () =>
          executerAction(
            courrier.id, "instructions-dept",
            { instructions: champsAction.instructions || "" },
            "Instructions enregistrées."
          ),
      },
      commenter: {
        titre: `Commenter ${courrier.numero}`,
        champs: [["commentaire", "Commentaire", "textarea"]],
        envoyer: () =>
          executerAction(
            courrier.id, "commenter",
            { commentaire: champsAction.commentaire || "" },
            "Commentaire ajouté."
          ),
      },
    }[type];

    if (!configuration) return null;

    const servicesDuDepartement = services.filter(
      (service) =>
        !courrier.departement || service.departement === courrier.departement
    );

    return (
      <section className="carte formulaire">
        <h2>{configuration.titre}</h2>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            configuration.envoyer();
          }}
        >
          {configuration.champs.map(([nom, label, typeChamp]) => (
            <div key={nom}>
              <label htmlFor={`action-${nom}`}>{label}</label>

              {typeChamp === "textarea" && (
                <textarea
                  id={`action-${nom}`}
                  rows="3"
                  value={champsAction[nom] || ""}
                  onChange={(event) =>
                    setChampsAction({ ...champsAction, [nom]: event.target.value })
                  }
                />
              )}

              {typeChamp === "departement" && (
                <select
                  id={`action-${nom}`}
                  required
                  value={champsAction[nom] || ""}
                  onChange={(event) =>
                    setChampsAction({ ...champsAction, [nom]: event.target.value })
                  }
                >
                  <option value="">-- Choisir un département --</option>
                  {departements.map((departement) => (
                    <option key={departement.id} value={departement.id}>
                      {departement.code} - {departement.nom}
                      {courrier.affectations_provisoires?.includes(departement.id)
                        ? " (proposé par le Bureau d'Ordre)"
                        : ""}
                    </option>
                  ))}
                </select>
              )}

              {typeChamp === "service" && (
                <select
                  id={`action-${nom}`}
                  required
                  value={champsAction[nom] || ""}
                  onChange={(event) =>
                    setChampsAction({ ...champsAction, [nom]: event.target.value })
                  }
                >
                  <option value="">-- Choisir un service --</option>
                  {servicesDuDepartement.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.code} - {service.nom}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ))}

          <div className="actions">
            <button type="submit">Confirmer</button>
            <button
              type="button"
              className="bouton-secondaire"
              onClick={() => setPanneauAction(null)}
            >
              Annuler
            </button>
          </div>
        </form>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Statistiques et rapports (§5.10)
  // ------------------------------------------------------------------

  function rendreTableauStat(titre, lignes, libelleColonne = "Catégorie") {
    if (!lignes || lignes.length === 0) return null;
    return (
      <div className="bloc-stat">
        <h3>{titre}</h3>
        <table>
          <thead>
            <tr>
              <th>{libelleColonne}</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {lignes.map((ligne, index) => (
              <tr key={index}>
                <td>{ligne.label || ligne.mois}</td>
                <td>{ligne.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function rendreStatistiques() {
    if (!statistiques) {
      return (
        <section className="carte">
          <p>Chargement des statistiques...</p>
        </section>
      );
    }
    const stats = statistiques;

    return (
      <section className="carte">
        <h2>
          Statistiques et rapports
          {stats.role_rapport === "departement" ? ` — ${stats.departement}` : ""}
        </h2>

        <div className="indicateurs">
          {Object.entries({
            courriers: "Courriers",
            entrants: "Entrants",
            sortants: "Sortants",
            traites: "Traités",
            en_cours: "En cours",
            en_retard: "En retard",
            retournes_dg: "Retours au DG",
            avec_instructions_dg: "Avec instructions DG",
          })
            .filter(([cle]) => stats.totaux && cle in stats.totaux)
            .map(([cle, libelle]) => (
              <div key={cle} className="indicateur">
                <strong>{stats.totaux[cle]}</strong>
                <span>{libelle}</span>
              </div>
            ))}

          {stats.avec_instructions !== undefined && (
            <div className="indicateur">
              <strong>{stats.avec_instructions}</strong>
              <span>Avec instructions</span>
            </div>
          )}
        </div>

        {stats.delais && (
          <div className="indicateurs">
            <div className="indicateur">
              <strong>
                {stats.delais.source_vers_reception ?? "—"}
                {stats.delais.source_vers_reception != null ? " j" : ""}
              </strong>
              <span>Délai source → réception</span>
            </div>
            <div className="indicateur">
              <strong>
                {stats.delais.reception_vers_affectation ?? "—"}
                {stats.delais.reception_vers_affectation != null ? " j" : ""}
              </strong>
              <span>Délai réception → affectation</span>
            </div>
            <div className="indicateur">
              <strong>
                {stats.delais.traitement_moyen ?? "—"}
                {stats.delais.traitement_moyen != null ? " j" : ""}
              </strong>
              <span>Délai moyen de traitement</span>
            </div>
          </div>
        )}

        {stats.affectation_provisoire && (
          <div className="indicateurs">
            <div className="indicateur">
              <strong>{stats.affectation_provisoire.avec}</strong>
              <span>Avec affectation provisoire</span>
            </div>
            <div className="indicateur">
              <strong>{stats.affectation_provisoire.sans}</strong>
              <span>Sans affectation provisoire</span>
            </div>
          </div>
        )}

        <div className="grille-stats">
          {rendreTableauStat("Courriers par mois", stats.par_mois, "Mois")}
          {rendreTableauStat("Courriers par département", stats.par_departement, "Département")}
          {rendreTableauStat("Courriers par service", stats.par_service, "Service")}
          {rendreTableauStat(
            "Par statut",
            stats.par_statut?.map((ligne) => ({
              ...ligne,
              label: libellesStatut[ligne.label] || ligne.label,
            })),
            "Statut"
          )}
          {rendreTableauStat("Retours au DG par département", stats.retours_par_departement, "Département")}
          {rendreTableauStat("Modifications par utilisateur", stats.modifications_par_utilisateur, "Utilisateur")}
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Administration — rendu (§5.11, §5.12)
  // ------------------------------------------------------------------

  function rendreFormulaireAdmin() {
    if (!formulaireAdmin) return null;
    const { type, id, valeurs } = formulaireAdmin;

    const modifier = (champ, valeur) =>
      setFormulaireAdmin({
        ...formulaireAdmin,
        valeurs: { ...valeurs, [champ]: valeur },
      });

    const titres = {
      utilisateurs: id ? "Modifier l'utilisateur" : "Nouvel utilisateur",
      departements: id ? "Modifier le département" : "Nouveau département",
      services: id ? "Modifier le service" : "Nouveau service",
    };

    return (
      <form className="formulaire-admin" onSubmit={enregistrerElementAdmin}>
        <h3>{titres[type]}</h3>

        <div className="grille">
          {type === "utilisateurs" ? (
            <>
              <div>
                <label htmlFor="admin-username">Identifiant *</label>
                <input
                  id="admin-username"
                  value={valeurs.username || ""}
                  onChange={(e) => modifier("username", e.target.value)}
                  required
                />
              </div>
              <div>
                <label htmlFor="admin-email">Email professionnel</label>
                <input
                  id="admin-email"
                  type="email"
                  value={valeurs.email || ""}
                  onChange={(e) => modifier("email", e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="admin-prenom">Prénom</label>
                <input
                  id="admin-prenom"
                  value={valeurs.first_name || ""}
                  onChange={(e) => modifier("first_name", e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="admin-nom">Nom</label>
                <input
                  id="admin-nom"
                  value={valeurs.last_name || ""}
                  onChange={(e) => modifier("last_name", e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="admin-role">Rôle *</label>
                <select
                  id="admin-role"
                  value={valeurs.role || ""}
                  onChange={(e) => modifier("role", e.target.value)}
                  required
                >
                  <option value="">-- Choisir un rôle --</option>
                  {Object.entries(libellesRole).map(([valeur, libelle]) => (
                    <option key={valeur} value={valeur}>{libelle}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="admin-departement">Département</label>
                <select
                  id="admin-departement"
                  value={valeurs.departement || ""}
                  onChange={(e) => {
                    modifier("departement", e.target.value);
                    setFormulaireAdmin((precedent) => ({
                      ...precedent,
                      valeurs: {
                        ...precedent.valeurs,
                        departement: e.target.value,
                        service: "",
                      },
                    }));
                  }}
                >
                  <option value="">-- Aucun --</option>
                  {donneesAdmin.departements
                    .filter((d) => d.statut === "actif")
                    .map((d) => (
                      <option key={d.id} value={d.id}>{d.code} - {d.nom}</option>
                    ))}
                </select>
              </div>
              <div>
                <label htmlFor="admin-service">Service</label>
                <select
                  id="admin-service"
                  value={valeurs.service || ""}
                  onChange={(e) => modifier("service", e.target.value)}
                >
                  <option value="">-- Aucun --</option>
                  {donneesAdmin.services
                    .filter(
                      (s) =>
                        s.statut === "actif" &&
                        (!valeurs.departement ||
                          s.departement === Number(valeurs.departement))
                    )
                    .map((s) => (
                      <option key={s.id} value={s.id}>{s.code} - {s.nom}</option>
                    ))}
                </select>
              </div>
              <div>
                <label htmlFor="admin-mdp">
                  {id ? "Nouveau mot de passe (laisser vide pour conserver)" : "Mot de passe initial *"}
                </label>
                <input
                  id="admin-mdp"
                  type="password"
                  value={valeurs.mot_de_passe || ""}
                  onChange={(e) => modifier("mot_de_passe", e.target.value)}
                  required={!id}
                  placeholder="8 caractères minimum"
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <label htmlFor="admin-nom-entite">Nom *</label>
                <input
                  id="admin-nom-entite"
                  value={valeurs.nom || ""}
                  onChange={(e) => modifier("nom", e.target.value)}
                  required
                />
              </div>
              <div>
                <label htmlFor="admin-code">Code * (ex. RH, FIN)</label>
                <input
                  id="admin-code"
                  value={valeurs.code || ""}
                  onChange={(e) => modifier("code", e.target.value)}
                  maxLength={10}
                  required
                />
              </div>
              {type === "services" && (
                <div>
                  <label htmlFor="admin-dept-service">Département *</label>
                  <select
                    id="admin-dept-service"
                    value={valeurs.departement || ""}
                    onChange={(e) => modifier("departement", e.target.value)}
                    required
                  >
                    <option value="">-- Choisir un département --</option>
                    {donneesAdmin.departements
                      .filter((d) => d.statut === "actif")
                      .map((d) => (
                        <option key={d.id} value={d.id}>{d.code} - {d.nom}</option>
                      ))}
                  </select>
                </div>
              )}
              <div>
                <label htmlFor="admin-responsable">Responsable</label>
                <select
                  id="admin-responsable"
                  value={valeurs.responsable || ""}
                  onChange={(e) => modifier("responsable", e.target.value)}
                >
                  <option value="">-- Aucun --</option>
                  {donneesAdmin.utilisateurs
                    .filter((u) => u.is_active)
                    .map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.nom_complet} ({u.role_label})
                      </option>
                    ))}
                </select>
              </div>
            </>
          )}
        </div>

        <div className="actions">
          <button type="submit">{id ? "Enregistrer" : "Créer"}</button>
          <button
            type="button"
            className="bouton-secondaire"
            onClick={() => setFormulaireAdmin(null)}
          >
            Annuler
          </button>
        </div>
      </form>
    );
  }

  function rendreAdministration() {
    const onglets = [
      ["utilisateurs", "Utilisateurs", donneesAdmin.utilisateurs.length],
      ["departements", "Départements", donneesAdmin.departements.length],
      ["services", "Services", donneesAdmin.services.length],
    ];

    const libellesBouton = {
      utilisateurs: "+ Nouvel utilisateur",
      departements: "+ Nouveau département",
      services: "+ Nouveau service",
    };

    return (
      <section className="carte">
        <div className="entete-fiche">
          <h2>Administration</h2>
          <button onClick={() => ouvrirFormulaireAdmin(ongletAdmin, null)}>
            {libellesBouton[ongletAdmin]}
          </button>
        </div>

        <div className="onglets">
          {onglets.map(([cle, libelle, total]) => (
            <button
              key={cle}
              className={`onglet ${ongletAdmin === cle ? "onglet-actif" : ""}`}
              onClick={() => {
                setOngletAdmin(cle);
                setFormulaireAdmin(null);
                window.location.hash = `#/administration/${cle}`;
              }}
            >
              {libelle} <span className="badge">{total}</span>
            </button>
          ))}
        </div>

        {rendreFormulaireAdmin()}

        {ongletAdmin === "utilisateurs" && (
          <table>
            <thead>
              <tr>
                <th>Identifiant</th>
                <th>Nom complet</th>
                <th>Rôle</th>
                <th>Département</th>
                <th>Service</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {donneesAdmin.utilisateurs.map((utilisateur) => (
                <tr key={utilisateur.id}>
                  <td>{utilisateur.username}</td>
                  <td>{utilisateur.nom_complet}</td>
                  <td><span className="badge">{utilisateur.role_label || "—"}</span></td>
                  <td>{utilisateur.departement_nom || "—"}</td>
                  <td>{utilisateur.service_nom || "—"}</td>
                  <td>
                    <span
                      className={`badge ${utilisateur.is_active ? "statut-valide" : "statut-archive"}`}
                    >
                      {utilisateur.is_active ? "Actif" : "Inactif"}
                    </span>
                  </td>
                  <td className="cellule-actions">
                    <button
                      className="petit-bouton bouton-discret"
                      onClick={() => ouvrirFormulaireAdmin("utilisateurs", utilisateur)}
                    >
                      Modifier
                    </button>
                    <button
                      className={`petit-bouton ${utilisateur.is_active ? "bouton-danger" : ""}`}
                      onClick={() => basculerStatutAdmin("utilisateurs", utilisateur)}
                    >
                      {utilisateur.is_active ? "Désactiver" : "Réactiver"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {ongletAdmin !== "utilisateurs" && (
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Nom</th>
                {ongletAdmin === "services" ? <th>Département</th> : <th>Services</th>}
                <th>Responsable</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {donneesAdmin[ongletAdmin].map((element) => (
                <tr key={element.id}>
                  <td><strong>{element.code}</strong></td>
                  <td>{element.nom}</td>
                  <td>
                    {ongletAdmin === "services"
                      ? element.departement_nom || "—"
                      : `${element.nombre_services} service(s)`}
                  </td>
                  <td>{element.responsable_nom || "—"}</td>
                  <td>
                    <span
                      className={`badge ${element.statut === "actif" ? "statut-valide" : "statut-archive"}`}
                    >
                      {element.statut === "actif" ? "Actif" : "Inactif"}
                    </span>
                  </td>
                  <td className="cellule-actions">
                    <button
                      className="petit-bouton bouton-discret"
                      onClick={() => ouvrirFormulaireAdmin(ongletAdmin, element)}
                    >
                      Modifier
                    </button>
                    <button
                      className={`petit-bouton ${element.statut === "actif" ? "bouton-danger" : ""}`}
                      onClick={() => basculerStatutAdmin(ongletAdmin, element)}
                    >
                      {element.statut === "actif" ? "Désactiver" : "Réactiver"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Journal d'activité — rendu (§4.2)
  // ------------------------------------------------------------------

  function rendreJournal() {
    if (!journal) {
      return (
        <section className="carte">
          <p>Chargement du journal d'activité...</p>
        </section>
      );
    }

    const entrees = journal.results || [];
    const taillePage = 50;
    const pageCourante = filtresJournal.page;
    const nombrePages = Math.max(1, Math.ceil((journal.count || 0) / taillePage));

    return (
      <section className="carte">
        <div className="entete-fiche">
          <h2>Journal d'activité</h2>
          <span className="aide-champ">
            {journal.count} action{journal.count > 1 ? "s" : ""} enregistrée
            {journal.count > 1 ? "s" : ""}
          </span>
        </div>

        <form
          className="filtres-journal"
          onSubmit={(event) => {
            event.preventDefault();
            const suivant = { ...filtresJournal, page: 1 };
            setFiltresJournal(suivant);
            chargerJournal(suivant);
          }}
        >
          <div className="grille">
            <div>
              <label htmlFor="journal-q">Recherche libre</label>
              <input
                id="journal-q"
                placeholder="N° courrier, objet, utilisateur, commentaire..."
                value={filtresJournal.q}
                onChange={(event) =>
                  setFiltresJournal({ ...filtresJournal, q: event.target.value })
                }
              />
            </div>

            <div>
              <label htmlFor="journal-action">Type d'action</label>
              <select
                id="journal-action"
                value={filtresJournal.action}
                onChange={(event) =>
                  setFiltresJournal({ ...filtresJournal, action: event.target.value })
                }
              >
                <option value="">Toutes les actions</option>
                {actionsJournal.map((action) => (
                  <option key={action.valeur} value={action.valeur}>
                    {action.libelle}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="journal-utilisateur">Utilisateur</label>
              <select
                id="journal-utilisateur"
                value={filtresJournal.utilisateur}
                onChange={(event) =>
                  setFiltresJournal({
                    ...filtresJournal,
                    utilisateur: event.target.value,
                  })
                }
              >
                <option value="">Tous les utilisateurs</option>
                {utilisateurs.map((utilisateur) => (
                  <option key={utilisateur.id} value={utilisateur.id}>
                    {utilisateur.first_name || utilisateur.last_name
                      ? `${utilisateur.first_name} ${utilisateur.last_name}`.trim()
                      : utilisateur.username}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="journal-du">Du</label>
              <input
                id="journal-du"
                type="date"
                value={filtresJournal.du}
                onChange={(event) =>
                  setFiltresJournal({ ...filtresJournal, du: event.target.value })
                }
              />
            </div>

            <div>
              <label htmlFor="journal-au">Au</label>
              <input
                id="journal-au"
                type="date"
                value={filtresJournal.au}
                onChange={(event) =>
                  setFiltresJournal({ ...filtresJournal, au: event.target.value })
                }
              />
            </div>
          </div>

          <div className="actions">
            <button type="submit">Filtrer</button>
            <button
              type="button"
              className="bouton-secondaire"
              onClick={() => {
                const vides = {
                  q: "",
                  action: "",
                  utilisateur: "",
                  du: "",
                  au: "",
                  page: 1,
                };
                setFiltresJournal(vides);
                chargerJournal(vides);
              }}
            >
              Réinitialiser
            </button>
          </div>
        </form>

        {entrees.length === 0 ? (
          <p className="aide-champ">Aucune action ne correspond à ces critères.</p>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>Date et heure</th>
                  <th>Utilisateur</th>
                  <th>Rôle</th>
                  <th>Action</th>
                  <th>Courrier</th>
                  <th>Détail</th>
                </tr>
              </thead>
              <tbody>
                {entrees.map((entree) => (
                  <tr key={entree.id}>
                    <td>{new Date(entree.date).toLocaleString("fr-FR")}</td>
                    <td>{entree.auteur_nom}</td>
                    <td>
                      <span className="badge">{entree.auteur_role}</span>
                    </td>
                    <td>{entree.action_label}</td>
                    <td>
                      {entree.courrier_numero ? (
                        <>
                          <strong>{entree.courrier_numero}</strong>
                          <br />
                          <span className="aide-champ">{entree.courrier_objet}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {entree.champ_modifie
                        ? `${entree.champ_modifie} : ${entree.ancienne_valeur} → ${entree.nouvelle_valeur}`
                        : entree.commentaire}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="pagination">
              <button
                className="petit-bouton bouton-secondaire"
                disabled={!journal.previous}
                onClick={() => changerPageJournal(-1)}
              >
                ← Précédent
              </button>
              <span className="aide-champ">
                Page {pageCourante} sur {nombrePages}
              </span>
              <button
                className="petit-bouton bouton-secondaire"
                disabled={!journal.next}
                onClick={() => changerPageJournal(1)}
              >
                Suivant →
              </button>
            </div>
          </>
        )}
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Fiche détaillée d'un courrier (§5.3.4)
  // ------------------------------------------------------------------

  function rendreDetail() {
    if (!courrierDetail) return null;
    const courrier = courrierDetail;

    return (
      <section className="carte fiche-courrier">
        <div className="entete-fiche">
          <h2>
            {courrier.numero} — {courrier.objet}
          </h2>
          <button
            className="bouton-secondaire"
            onClick={() => setCourrierDetail(null)}
          >
            Fermer
          </button>
        </div>

        <div className="grille-fiche">
          <p><strong>Numéro source :</strong> {courrier.numero_source}</p>
          <p><strong>Date source :</strong> {formaterDate(courrier.date_source)}</p>
          <p><strong>Date de réception :</strong> {formaterDate(courrier.date_reception)}</p>
          <p><strong>Type :</strong> {courrier.type_courrier === "entrant" ? "Entrant" : "Sortant"}</p>
          <p><strong>Catégorie :</strong> {courrier.categorie}</p>
          <p><strong>Priorité :</strong> {libellesPriorite[courrier.priorite] || courrier.priorite}</p>
          <p><strong>Statut :</strong> {libellesStatut[courrier.statut] || courrier.statut}</p>
          <p><strong>Expéditeur :</strong> {courrier.expediteur || "—"}</p>
          <p><strong>Destinataire :</strong> {courrier.destinataire || "—"}</p>
          <p><strong>Date limite :</strong> {formaterDate(courrier.date_echeance)}</p>
          {"affectations_provisoires_nom" in courrier && (
            <p>
              <strong>Affectations provisoires :</strong>{" "}
              {courrier.affectations_provisoires_nom?.join(", ") || "—"}
            </p>
          )}
          <p><strong>Département (finale) :</strong> {courrier.departement_nom || "—"}</p>
          <p><strong>Service :</strong> {courrier.service_nom || "—"}</p>
        </div>

        {courrier.description && (
          <p className="description-fiche">{courrier.description}</p>
        )}

        <div className="bloc-document">
          <h3>Document numérisé</h3>

          {courrier.fichier ? (
            <p className="ligne-document">
              <a
                href={courrier.fichier}
                target="_blank"
                rel="noreferrer"
                className="lien-document"
              >
                📄 {courrier.fichier.split("/").pop()}
              </a>
              <span className="aide-champ">— cliquer pour ouvrir ou télécharger</span>
            </p>
          ) : (
            <p className="aide-champ">Aucun document joint à ce courrier.</p>
          )}

          {courrier.statut !== "archive" && (
            <div className="zone-document">
              <input
                id={`document-fiche-${courrier.id}`}
                type="file"
                accept={FORMATS_DOCUMENT}
                className="champ-fichier"
                onChange={(event) => {
                  const fichier = event.target.files[0];
                  if (fichier) joindreDocumentAuCourrier(courrier, fichier);
                  event.target.value = "";
                }}
              />
              <label
                htmlFor={`document-fiche-${courrier.id}`}
                className="bouton-fichier"
              >
                📎 {courrier.fichier ? "Remplacer le document" : "Joindre un document scanné"}
              </label>
              <span className="aide-champ">PDF, Word, JPG, PNG — 10 Mo max.</span>
            </div>
          )}
        </div>

        {"instructions_dg" in courrier && courrier.instructions_dg && (
          <div className="bloc-instructions">
            <h3>Instructions du Directeur Général</h3>
            <p>{courrier.instructions_dg}</p>
          </div>
        )}

        {"instructions_chef_dept" in courrier && courrier.instructions_chef_dept && (
          <div className="bloc-instructions">
            <h3>Instructions du Chef de Département</h3>
            <p>{courrier.instructions_chef_dept}</p>
          </div>
        )}

        {courrier.historique && courrier.historique.length > 0 && (
          <>
            <h3>Historique complet</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Par</th>
                  <th>Action</th>
                  <th>Détail</th>
                </tr>
              </thead>
              <tbody>
                {courrier.historique.map((entree) => (
                  <tr key={entree.id}>
                    <td>{new Date(entree.date).toLocaleString("fr-FR")}</td>
                    <td>{entree.auteur_nom}</td>
                    <td>{entree.action_label}</td>
                    <td>
                      {entree.champ_modifie
                        ? `${entree.champ_modifie} : ${entree.ancienne_valeur} → ${entree.nouvelle_valeur}`
                        : entree.commentaire}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Écran de connexion
  // ------------------------------------------------------------------

  if (!token) {
    return (
      <main className="page-connexion">
        <section className="connexion-carte">
          <div className="connexion-formulaire">
            <div className="marque">
              <span className="marque-icone" aria-hidden="true">✉</span>
              <span>Gestion des Courriers</span>
            </div>

            <div className="connexion-introduction">
              <p className="sur-titre">ESPACE SÉCURISÉ</p>
              <h1>Bienvenue</h1>
              <p>Connectez-vous pour consulter et traiter vos courriers centralisés.</p>
            </div>

            <form className="formulaire-connexion" onSubmit={seConnecter}>
              <label htmlFor="username">Adresse e-mail ou identifiant</label>
              <div className="champ-icone">
                <span aria-hidden="true">@</span>
                <input
                  id="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  placeholder="nom@organisation.ma"
                  required
                />
              </div>

              <label htmlFor="password">Mot de passe</label>
              <div className="champ-icone">
                <span aria-hidden="true">⌁</span>
                <input
                  id="password"
                  type={afficherMotDePasse ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  placeholder="Votre mot de passe"
                  required
                />
                <button
                  className="basculer-mot-de-passe"
                  type="button"
                  onClick={() => setAfficherMotDePasse(!afficherMotDePasse)}
                  aria-label={afficherMotDePasse ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                >
                  {afficherMotDePasse ? "Masquer" : "Afficher"}
                </button>
              </div>

              <div className="options-connexion">
                <label className="memoriser">
                  <input
                    type="checkbox"
                    checked={seSouvenir}
                    onChange={(event) => setSeSouvenir(event.target.checked)}
                  />
                  <span>Se souvenir de moi</span>
                </label>
              </div>

              {erreur && <p className="erreur">{erreur}</p>}

              <button className="bouton-connexion" type="submit" disabled={chargement}>
                {chargement ? "Connexion en cours..." : "Se connecter"}
                <span aria-hidden="true">→</span>
              </button>
            </form>
          </div>

          <aside className="connexion-visuel" aria-label="Centralisation des courriers">
            <img
              className="image-connexion"
              src={illustrationConnexion}
              alt="Illustration de la centralisation numérique des courriers"
            />
            <div className="voile-illustration" />
            <div className="visuel-grille" />
            <div className="visuel-courrier courrier-haut">
              <span>✉</span>
              <small>Courriers entrants</small>
            </div>
            <div className="visuel-courrier courrier-bas">
              <span>↗</span>
              <small>Courriers sortants</small>
            </div>
            <div className="visuel-centre">
              <div className="visuel-logo">GC</div>
              <h2>Tous vos courriers,<br />un seul espace.</h2>
              <p>Centralisez, affectez et suivez chaque échange en toute simplicité.</p>
            </div>
            <div className="pastille pastille-une" />
            <div className="pastille pastille-deux" />
          </aside>
        </section>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Changement de mot de passe obligatoire (première connexion)
  // ------------------------------------------------------------------

  if (profil?.doit_changer_mot_de_passe) {
    return (
      <main className="page-connexion">
        <section className="connexion-carte">
          <div className="connexion-formulaire">
            <div className="marque">
              <span className="marque-icone" aria-hidden="true">✉</span>
              <span>Gestion des Courriers</span>
            </div>

            <div className="connexion-introduction">
              <p className="sur-titre">PREMIÈRE CONNEXION</p>
              <h1>Changez votre mot de passe</h1>
              <p>
                Pour votre sécurité, vous devez définir un nouveau mot de passe
                personnel avant d'accéder à l'application.
              </p>
            </div>

            <form className="formulaire-connexion" onSubmit={changerMotDePasse}>
              <label htmlFor="ancien">Mot de passe actuel</label>
              <div className="champ-icone">
                <span aria-hidden="true">⌁</span>
                <input
                  id="ancien"
                  type="password"
                  value={motsDePasse.ancien}
                  onChange={(event) =>
                    setMotsDePasse({ ...motsDePasse, ancien: event.target.value })
                  }
                  autoComplete="current-password"
                  required
                />
              </div>

              <label htmlFor="nouveau">Nouveau mot de passe</label>
              <div className="champ-icone">
                <span aria-hidden="true">⌁</span>
                <input
                  id="nouveau"
                  type="password"
                  value={motsDePasse.nouveau}
                  onChange={(event) =>
                    setMotsDePasse({ ...motsDePasse, nouveau: event.target.value })
                  }
                  autoComplete="new-password"
                  placeholder="8 caractères minimum"
                  required
                />
              </div>

              <label htmlFor="confirmation">Confirmer le nouveau mot de passe</label>
              <div className="champ-icone">
                <span aria-hidden="true">⌁</span>
                <input
                  id="confirmation"
                  type="password"
                  value={motsDePasse.confirmation}
                  onChange={(event) =>
                    setMotsDePasse({
                      ...motsDePasse,
                      confirmation: event.target.value,
                    })
                  }
                  autoComplete="new-password"
                  required
                />
              </div>

              {erreur && <p className="erreur">{erreur}</p>}

              <button className="bouton-connexion" type="submit">
                Valider le nouveau mot de passe
                <span aria-hidden="true">→</span>
              </button>

              <button
                type="button"
                className="bouton-secondaire"
                onClick={seDeconnecter}
              >
                Se déconnecter
              </button>
            </form>
          </div>

          <aside className="connexion-visuel" aria-label="Sécurité du compte">
            <img
              className="image-connexion"
              src={illustrationConnexion}
              alt="Illustration de la sécurité du compte"
            />
            <div className="voile-illustration" />
            <div className="visuel-grille" />
            <div className="visuel-centre">
              <div className="visuel-logo">🔒</div>
              <h2>Votre compte,<br />votre mot de passe.</h2>
              <p>Un mot de passe personnel et sécurisé protège vos courriers.</p>
            </div>
          </aside>
        </section>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Tableau de bord
  // ------------------------------------------------------------------

  const estEntrantFormulaire = formulaire.type_courrier === "entrant";
  const estPageCourriers =
    route === "/courriers" ||
    route === "/" ||
    (!["/courriers/nouveau", "/statistiques", "/journal", "/recherche"].includes(route) &&
      !route.startsWith("/administration"));

  return (
    <main className="conteneur">
      <header className="entete">
        <div className="profil-utilisateur" title="Utilisateur connecté">
          <div className="avatar" aria-hidden="true">
            {(profil?.nom_complet || profil?.username || "?")
              .split(" ")
              .map((mot) => mot[0])
              .slice(0, 2)
              .join("")
              .toUpperCase()}
          </div>
          <div className="profil-texte">
            <strong>{profil?.nom_complet || profil?.username}</strong>
            <span>
              {libellesRole[role] || role}
              {profil?.departement_nom ? ` — ${profil.departement_nom}` : ""}
              {profil?.service_nom ? ` — ${profil.service_nom}` : ""}
            </span>
          </div>
        </div>

        <nav className="barre-navigation" aria-label="Navigation principale">
          <a
            href="#/courriers"
            className={`bouton-nav ${estPageCourriers ? "bouton-nav-actif" : ""}`}
            title="Tableau de bord et suivi des courriers"
          >
            📋 Tableau de bord
          </a>

          {(role === "bureau_ordre" || role === "admin") && (
            <a
              href="#/courriers/nouveau"
              className={`bouton-nav ${route === "/courriers/nouveau" ? "bouton-nav-actif" : ""}`}
              title="Enregistrer un nouveau courrier entrant ou sortant"
            >
              ➕ Enregistrer un courrier
            </a>
          )}

          {["dg", "secretaire", "admin", "chef_departement"].includes(role) && (
            <a
              href="#/statistiques"
              className={`bouton-nav ${route === "/statistiques" ? "bouton-nav-actif" : ""}`}
              title="Statistiques et indicateurs de performance"
            >
              📊 Statistiques
            </a>
          )}

          {role === "admin" && (
            <>
              <a
                href="#/administration"
                className={`bouton-nav ${route.startsWith("/administration") ? "bouton-nav-actif" : ""}`}
                title="Administration des utilisateurs, départements et services"
              >
                ⚙️ Administration
              </a>

              <a
                href="#/journal"
                className={`bouton-nav ${route === "/journal" ? "bouton-nav-actif" : ""}`}
                title="Journal d'audit et historique des activités"
              >
                🗂 Journal d'activité
              </a>
            </>
          )}

          <a
            href="#/recherche"
            className={`bouton-nav ${route === "/recherche" ? "bouton-nav-actif" : ""}`}
            title="Rechercher des courriers par critères"
          >
            🔍 Recherche
          </a>
        </nav>

        <div className="actions">

          <button
            className="bouton-notification"
            onClick={() => setAfficherNotifications(!afficherNotifications)}
          >
            Notifications ({compteurNotifications.non_lues})
          </button>

          <button className="bouton-secondaire" onClick={seDeconnecter}>
            Se déconnecter
          </button>
        </div>
      </header>

      {erreur && <p className="erreur">{erreur}</p>}
      {message && <p className="message">{message}</p>}

      {afficherNotifications && (
        <section className="carte panneau-notifications">
          <div className="entete-fiche">
            <h2>Mes notifications</h2>

            <div className="actions">
              <span className="aide-champ">
                {compteurNotifications.non_lues} non lue
                {compteurNotifications.non_lues > 1 ? "s" : ""} sur{" "}
                {compteurNotifications.total}
                {compteurNotifications.total > notifications.length
                  ? ` — ${notifications.length} plus récentes affichées`
                  : ""}
              </span>

              {compteurNotifications.non_lues > 0 && (
                <button className="petit-bouton" onClick={toutMarquerLues}>
                  Tout marquer comme lu
                </button>
              )}
            </div>
          </div>

          {notifications.length === 0 ? (
            <p>Aucune notification.</p>
          ) : (
            notifications.map((notification) => {
              const courrierLie = courriers.find(
                (courrier) => courrier.id === notification.courrier
              );
              return (
                <article
                  key={notification.id}
                  className={`notification ${notification.lu ? "lue" : "non-lue"} ${
                    courrierLie ? "notification-cliquable" : ""
                  }`}
                  onClick={() => {
                    if (!courrierLie) return;
                    setCourrierDetail(courrierLie);
                    setAfficherNotifications(false);
                    if (!estPageCourriers) window.location.hash = "#/courriers";
                    if (!notification.lu) marquerNotificationLue(notification.id);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                  title={courrierLie ? "Cliquer pour ouvrir la fiche du courrier" : undefined}
                >
                  <div>
                    <strong>{notification.type.toUpperCase()}</strong>
                    <p>{notification.message}</p>

                    {notification.courrier_numero && (
                      <small>
                        Courrier : {notification.courrier_numero}
                        {courrierLie ? " — cliquer pour ouvrir la fiche" : ""}
                      </small>
                    )}
                  </div>

                  {!notification.lu && (
                    <button
                      className="petit-bouton"
                      onClick={(event) => {
                        event.stopPropagation();
                        marquerNotificationLue(notification.id);
                      }}
                    >
                      Marquer comme lue
                    </button>
                  )}
                </article>
              );
            })
          )}
        </section>
      )}

      {/* Page Enregistrer un courrier */}
      {route === "/courriers/nouveau" && (
        <>
          <div className="barre-retour">
            <a href="#/courriers" className="lien-retour" onClick={annulerEnregistrement}>
              ← Retour au tableau de bord
            </a>
          </div>

          <div className="titre-page">
            <h1>Enregistrer un courrier</h1>
            <p>Saisie et numérisation d'un nouveau courrier entrant ou sortant</p>
          </div>

          {(role === "bureau_ordre" || role === "admin") ? (
            <section className="carte formulaire">
              <h2>Formulaire d'enregistrement</h2>

              <form onSubmit={enregistrerCourrier}>
                <div className="grille">
                  <div>
                    <label htmlFor="type_courrier">Type de courrier</label>
                    <select
                      className="champ-select-uniforme"
                      id="type_courrier"
                      name="type_courrier"
                      value={formulaire.type_courrier}
                      onChange={modifierFormulaire}
                    >
                      <option value="entrant">Entrant</option>
                      <option value="sortant">Sortant</option>
                    </select>
                  </div>

                  <div>
                    <label htmlFor="objet">Objet *</label>
                    <input
                      id="objet"
                      name="objet"
                      value={formulaire.objet}
                      onChange={modifierFormulaire}
                      required
                    />
                  </div>

                  <div>
                    <label htmlFor="numero_source">Numéro source *</label>
                    <input
                      id="numero_source"
                      name="numero_source"
                      value={formulaire.numero_source}
                      onChange={modifierFormulaire}
                      placeholder="N° figurant sur le document original"
                      required
                    />
                  </div>

                  <div>
                    <label htmlFor="date_source">Date source *</label>
                    <input
                      id="date_source"
                      name="date_source"
                      type="date"
                      value={formulaire.date_source}
                      onChange={modifierFormulaire}
                      required
                    />
                  </div>

                  {estEntrantFormulaire ? (
                    <>
                      <div>
                        <label htmlFor="date_reception">Date de réception *</label>
                        <input
                          id="date_reception"
                          name="date_reception"
                          type="date"
                          value={formulaire.date_reception}
                          onChange={modifierFormulaire}
                          required
                        />
                      </div>

                      <div>
                        <label htmlFor="expediteur">Expéditeur *</label>
                        <input
                          id="expediteur"
                          name="expediteur"
                          value={formulaire.expediteur}
                          onChange={modifierFormulaire}
                          required
                        />
                      </div>

                      <fieldset className="choix-departements">
                        <legend>Affectations provisoires</legend>
                        <details className="selecteur-departements">
                          <summary>
                            {formulaire.affectations_provisoires.length
                              ? `${formulaire.affectations_provisoires.length} département(s) sélectionné(s)`
                              : "Sélectionner un ou plusieurs départements"}
                          </summary>
                          <ul className="liste-cases-departement">
                            {departements.map((dept) => (
                              <li key={dept.id}>
                                <label className="case-departement">
                                  <input
                                    type="checkbox"
                                    checked={formulaire.affectations_provisoires.includes(String(dept.id))}
                                    onChange={(event) =>
                                      setFormulaire((precedent) => {
                                        const selection = new Set(precedent.affectations_provisoires);
                                        if (event.target.checked) selection.add(String(dept.id));
                                        else selection.delete(String(dept.id));
                                        return {
                                          ...precedent,
                                          affectations_provisoires: Array.from(selection),
                                        };
                                      })
                                    }
                                  />
                                  <span>{dept.code} - {dept.nom}</span>
                                </label>
                              </li>
                            ))}
                          </ul>
                        </details>
                      </fieldset>
                    </>
                  ) : (
                    <div>
                      <label htmlFor="destinataire">Destinataire *</label>
                      <input
                        id="destinataire"
                        name="destinataire"
                        value={formulaire.destinataire}
                        onChange={modifierFormulaire}
                        required
                      />
                    </div>
                  )}

                  <div>
                    <label htmlFor="categorie">Catégorie</label>
                    <select
                      className="champ-select-uniforme"
                      id="categorie"
                      name="categorie"
                      value={formulaire.categorie}
                      onChange={modifierFormulaire}
                    >
                      <option value="administratif">Administratif</option>
                      <option value="juridique">Juridique</option>
                      <option value="financier">Financier</option>
                      <option value="reponse">Réponse</option>
                      <option value="demande">Demande</option>
                      <option value="notification">Notification</option>
                      <option value="autre">Autre</option>
                    </select>
                  </div>

                  <div>
                    <label htmlFor="priorite">Priorité</label>
                    <select
                      className="champ-select-uniforme"
                      id="priorite"
                      name="priorite"
                      value={formulaire.priorite}
                      onChange={modifierFormulaire}
                    >
                      <option value="normal">Normal</option>
                      <option value="urgent">Urgent</option>
                      <option value="tres_urgent">Très urgent</option>
                    </select>
                  </div>

                  <div>
                    <label htmlFor="date_echeance">Date d'échéance</label>
                    <input
                      id="date_echeance"
                      name="date_echeance"
                      type="date"
                      value={formulaire.date_echeance}
                      onChange={modifierFormulaire}
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="description">Description</label>
                  <textarea
                    id="description"
                    name="description"
                    rows="3"
                    value={formulaire.description}
                    onChange={modifierFormulaire}
                    placeholder="Précisions utiles sur le courrier..."
                  />
                </div>

                <div className="zone-fichier">
                  <label htmlFor="document_numerise">
                    Document numérisé (pièce jointe)
                  </label>
                  <input
                    id="document_numerise"
                    type="file"
                    accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                    onChange={(event) => {
                      setDocumentNumerise(event.target.files?.[0] || null);
                      setSuggestionsIA(null);
                    }}
                  />
                  {documentNumerise && (
                    <div className="actions-analyse-document">
                      <button
                        type="button"
                        className="bouton-secondaire petit-bouton"
                        onClick={analyserDocument}
                        disabled={analyseEnCours}
                      >
                        {analyseEnCours ? "Analyse locale en cours..." : "Analyser avec l'IA locale"}
                      </button>
                      <button
                        type="button"
                        className="bouton-discret petit-bouton"
                        onClick={() => {
                          setDocumentNumerise(null);
                          setSuggestionsIA(null);
                          document.getElementById("document_numerise").value = "";
                        }}
                        disabled={analyseEnCours}
                      >
                        Retirer
                      </button>
                    </div>
                  )}
                </div>
                {suggestionsIA && (
                  <section className="suggestions-ia" aria-live="polite">
                    <h3>Suggestions de l'IA locale</h3>
                    <dl>
                      {champsSuggestionsIA.map(([champ, libelle]) => (
                        <div key={champ} className={!suggestionsIA[champ] ? "suggestion-absente" : ""}>
                          <dt>{libelle}</dt>
                          <dd>{suggestionsIA[champ] || "Non détecté"}</dd>
                        </div>
                      ))}
                    </dl>
                    <p className="aide-champ">
                      Les valeurs détectées ont prérempli le formulaire ci-dessus. Vérifiez-les avant l'enregistrement.
                    </p>
                  </section>
                )}
                <p className="aide-champ">
                  Formats acceptés : PDF, Word, JPG, PNG — 10 Mo maximum.
                </p>

                <div className="actions">
                  <button type="submit">Enregistrer le courrier</button>
                  <a
                    href="#/courriers"
                    className="bouton-secondaire bouton-nav"
                    onClick={annulerEnregistrement}
                  >
                    Annuler
                  </a>
                </div>
              </form>
            </section>
          ) : (
            <section className="carte">
              <p className="erreur">
                Vous n'avez pas l'autorisation d'enregistrer de courriers.
              </p>
            </section>
          )}
        </>
      )}

      {/* Page Statistiques */}
      {route === "/statistiques" && (
        <>
          <div className="barre-retour">
            <a href="#/courriers" className="lien-retour">
              ← Retour au tableau de bord
            </a>
          </div>

          <div className="titre-page">
            <h1>Statistiques et rapports</h1>
            <p>Tableaux de bord d'analyse, volumétrie et indicateurs de performance</p>
          </div>

          {["dg", "secretaire", "admin", "chef_departement"].includes(role) ? (
            rendreStatistiques()
          ) : (
            <section className="carte">
              <p className="erreur">
                Vous n'avez pas l'autorisation d'accéder aux statistiques.
              </p>
            </section>
          )}
        </>
      )}

      {/* Page Administration */}
      {route.startsWith("/administration") && (
        <>
          <div className="barre-retour">
            <a href="#/courriers" className="lien-retour">
              ← Retour au tableau de bord
            </a>
          </div>

          <div className="titre-page">
            <h1>Administration du système</h1>
            <p>Gestion des utilisateurs, départements et services</p>
          </div>

          {role === "admin" ? (
            rendreAdministration()
          ) : (
            <section className="carte">
              <p className="erreur">
                Accès réservé aux administrateurs du système.
              </p>
            </section>
          )}
        </>
      )}

      {/* Page Journal d'activité */}
      {route === "/journal" && (
        <>
          <div className="barre-retour">
            <a href="#/courriers" className="lien-retour">
              ← Retour au tableau de bord
            </a>
          </div>

          <div className="titre-page">
            <h1>Journal d'activité</h1>
            <p>Historique d'audit et traçabilité des actions effectuées sur le système</p>
          </div>

          {role === "admin" ? (
            rendreJournal()
          ) : (
            <section className="carte">
              <p className="erreur">
                Accès réservé aux administrateurs du système.
              </p>
            </section>
          )}
        </>
      )}

      {/* Page Recherche */}
      {route === "/recherche" && (
        <>
          <div className="barre-retour">
            <a href="#/courriers" className="lien-retour">
              ← Retour au tableau de bord
            </a>
          </div>

          <div className="titre-page">
            <h1>Recherche</h1>
            <p>Rechercher des courriers par critères : objet, statut, période, département...</p>
          </div>

          <section className="carte formulaire">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                chargerCourriers(token);
              }}
            >
              <div className="grille">
                <div>
                  <label htmlFor="filtre-q">Recherche libre</label>
                  <input
                    id="filtre-q"
                    placeholder="N° interne, n° source, objet, expéditeur..."
                    value={filtres.q}
                    onChange={(event) =>
                      setFiltres({ ...filtres, q: event.target.value })
                    }
                  />
                </div>

                <div>
                  <label htmlFor="filtre-statut">Statut</label>
                  <select
                    id="filtre-statut"
                    value={filtres.statut}
                    onChange={(event) =>
                      setFiltres({ ...filtres, statut: event.target.value })
                    }
                  >
                    <option value="">Tous</option>
                    {Object.entries(libellesStatut).map(([valeur, libelle]) => (
                      <option key={valeur} value={valeur}>
                        {libelle}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="filtre-priorite">Priorité</label>
                  <select
                    id="filtre-priorite"
                    value={filtres.priorite}
                    onChange={(event) =>
                      setFiltres({ ...filtres, priorite: event.target.value })
                    }
                  >
                    <option value="">Toutes</option>
                    <option value="normal">Normal</option>
                    <option value="urgent">Urgent</option>
                    <option value="tres_urgent">Très urgent</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="filtre-type">Type</label>
                  <select
                    id="filtre-type"
                    value={filtres.type_courrier}
                    onChange={(event) =>
                      setFiltres({ ...filtres, type_courrier: event.target.value })
                    }
                  >
                    <option value="">Entrant et sortant</option>
                    <option value="entrant">Entrant</option>
                    <option value="sortant">Sortant</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="filtre-departement">Département</label>
                  <select
                    id="filtre-departement"
                    value={filtres.departement}
                    onChange={(event) =>
                      setFiltres({ ...filtres, departement: event.target.value })
                    }
                  >
                    <option value="">Tous</option>
                    {departements.map((departement) => (
                      <option key={departement.id} value={departement.id}>
                        {departement.code} - {departement.nom}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="filtre-service">Service</label>
                  <select
                    id="filtre-service"
                    value={filtres.service}
                    onChange={(event) =>
                      setFiltres({ ...filtres, service: event.target.value })
                    }
                  >
                    <option value="">Tous</option>
                    {services
                      .filter(
                        (service) =>
                          !filtres.departement ||
                          service.departement === Number(filtres.departement)
                      )
                      .map((service) => (
                        <option key={service.id} value={service.id}>
                          {service.code} - {service.nom}
                        </option>
                      ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="filtre-reception-du">Reçu du</label>
                  <input
                    id="filtre-reception-du"
                    type="date"
                    value={filtres.reception_du}
                    onChange={(event) =>
                      setFiltres({ ...filtres, reception_du: event.target.value })
                    }
                  />
                </div>

                <div>
                  <label htmlFor="filtre-reception-au">Reçu au</label>
                  <input
                    id="filtre-reception-au"
                    type="date"
                    value={filtres.reception_au}
                    onChange={(event) =>
                      setFiltres({ ...filtres, reception_au: event.target.value })
                    }
                  />
                </div>

                <div>
                  <label htmlFor="filtre-instructions">Avec instructions</label>
                  <select
                    id="filtre-instructions"
                    value={filtres.avec_instructions}
                    onChange={(event) =>
                      setFiltres({
                        ...filtres,
                        avec_instructions: event.target.value,
                      })
                    }
                  >
                    <option value="">Indifférent</option>
                    <option value="oui">Oui</option>
                    <option value="non">Non</option>
                  </select>
                </div>
              </div>

              <div className="actions">
                <button type="submit">Rechercher</button>
                <button
                  type="button"
                  className="bouton-secondaire"
                  onClick={() => {
                    setFiltres(filtresVides);
                    chargerCourriers(token, filtresVides);
                  }}
                >
                  Réinitialiser
                </button>
              </div>
            </form>
          </section>

          <section className="carte">
            <h2>Résultats</h2>
            {chargement ? (
              <p>Chargement des courriers...</p>
            ) : courriers.length === 0 ? (
              <p>Aucun résultat pour ces critères.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Numéro</th>
                    <th>N° source</th>
                    <th>Type</th>
                    <th>Objet</th>
                    <th>Priorité</th>
                    <th>Statut</th>
                    <th>Département</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {courriers.map((courrier) => (
                    <tr key={courrier.id}>
                      <td>
                        <button
                          className="lien-courrier"
                          onClick={() => {
                            setCourrierDetail(courrier);
                            window.scrollTo({ top: 0, behavior: "smooth" });
                          }}
                        >
                          {courrier.numero}
                        </button>
                      </td>
                      <td>{courrier.numero_source}</td>
                      <td>{courrier.type_courrier === "entrant" ? "Entrant" : "Sortant"}</td>
                      <td>
                        {courrier.objet}
                        {courrier.fichier && (
                          <span
                            className="badge-document"
                            title="Un document numérisé est joint"
                          >
                            📎
                          </span>
                        )}
                        {(courrier.instructions_dg || courrier.instructions_chef_dept) && (
                          <button
                            className="badge badge-instructions"
                            onClick={() => setCourrierDetail(courrier)}
                            title="Des instructions sont disponibles — cliquer pour les lire"
                          >
                            📩 Instructions
                          </button>
                        )}
                      </td>
                      <td>
                        <span className={`badge badge-${courrier.priorite}`}>
                          {libellesPriorite[courrier.priorite] || courrier.priorite}
                        </span>
                      </td>
                      <td>
                        <span className={`badge statut-${courrier.statut}`}>
                          {libellesStatut[courrier.statut] || courrier.statut}
                        </span>
                      </td>
                      <td>{courrier.departement_nom || "—"}</td>
                      <td className="cellule-actions">{actionsPour(courrier)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}

      {/* Page Tableau de bord / Liste des courriers */}
      {estPageCourriers && (
        <>
          <div className="titre-page">
            <h1>Tableau de bord</h1>
            <p>Suivi et traitement des courriers de votre périmètre</p>
          </div>

          {indicateurs.length > 0 && (
            <section className="indicateurs">
              {indicateurs.map(([libelle, valeur]) => (
                <div key={libelle} className="indicateur">
                  <strong>{valeur}</strong>
                  <span>{libelle}</span>
                </div>
              ))}
            </section>
          )}


          {rendrePanneauAction()}
          {rendreDetail()}

          <section className="carte">
            <h2>Courriers</h2>

            {chargement ? (
              <p>Chargement des courriers...</p>
            ) : courriers.length === 0 ? (
              <p>Aucun courrier dans votre périmètre.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Numéro</th>
                    <th>N° source</th>
                    <th>Type</th>
                    <th>Objet</th>
                    <th>Priorité</th>
                    <th>Statut</th>
                    <th>Département</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {courriers.map((courrier) => (
                    <tr key={courrier.id}>
                      <td>
                        <button
                          className="lien-courrier"
                          onClick={() => {
                            setCourrierDetail(courrier);
                            window.scrollTo({ top: 0, behavior: "smooth" });
                          }}
                        >
                          {courrier.numero}
                        </button>
                      </td>
                      <td>{courrier.numero_source}</td>
                      <td>{courrier.type_courrier === "entrant" ? "Entrant" : "Sortant"}</td>
                      <td>
                        {courrier.objet}
                        {courrier.fichier && (
                          <span
                            className="badge-document"
                            title="Un document numérisé est joint"
                          >
                            📎
                          </span>
                        )}
                        {(courrier.instructions_dg || courrier.instructions_chef_dept) && (
                          <button
                            className="badge badge-instructions"
                            onClick={() => setCourrierDetail(courrier)}
                            title="Des instructions sont disponibles — cliquer pour les lire"
                          >
                            📩 Instructions
                          </button>
                        )}
                      </td>
                      <td>
                        <span className={`badge badge-${courrier.priorite}`}>
                          {libellesPriorite[courrier.priorite] || courrier.priorite}
                        </span>
                      </td>
                      <td>
                        <span className={`badge statut-${courrier.statut}`}>
                          {libellesStatut[courrier.statut] || courrier.statut}
                        </span>
                      </td>
                      <td>{courrier.departement_nom || "—"}</td>
                      <td className="cellule-actions">{actionsPour(courrier)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </main>
  );
}

export default App;
