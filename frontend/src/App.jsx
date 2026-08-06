import { useEffect, useState } from "react";

const API_URL = "/api";

const libellesStatut = {
  recu: "Reçu",
  affecte: "Affecté",
  en_cours: "En cours",
  en_attente: "En attente",
  traite: "Traité",
  archive: "Archivé",
  brouillon: "Brouillon",
  en_validation: "En validation",
  valide: "Validé",
  envoye: "Envoyé",
};

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [courriers, setCourriers] = useState([]);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [chargement, setChargement] = useState(false);
const [notifications, setNotifications] = useState([]);
const [afficherNotifications, setAfficherNotifications] = useState(false);
const [courrierAAffecter, setCourrierAAffecter] = useState(null);
const [services, setServices] = useState([]);
const [utilisateurs, setUtilisateurs] = useState([]);
const [affectation, setAffectation] = useState({
  serviceId: "",
  utilisateurId: "",
  commentaire: "",
});

  // Helper centralisé : attache le token, gère l'expiration (401)
  async function apiFetch(url, options = {}, accessToken) {
    const tok = accessToken || token;
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    if (tok) headers["Authorization"] = `Bearer ${tok}`;

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
      // Token expiré ou invalide → déconnexion automatique
      localStorage.removeItem("access_token");
      setToken("");
      setRole("");
      setCourriers([]);
      setUsername("");
      throw new Error("Session expirée. Veuillez vous reconnecter.");
    }
    return response;
  }

  async function chargerCourriers(accessToken) {
    setChargement(true);
    setErreur("");

    try {
      const response = await apiFetch(`${API_URL}/courriers/`, {}, accessToken);

      if (!response.ok) {
        throw new Error("Impossible de charger les courriers.");
      }

      setCourriers(await response.json());
    } catch (error) {
      setErreur(error.message);
    } finally {
      setChargement(false);
    }
  }
async function chargerNotifications(accessToken) {
  try {
    const response = await apiFetch(
      `${API_URL}/notifications/`,
      {},
      accessToken
    );

    if (!response.ok) {
      throw new Error("Impossible de charger les notifications.");
    }

    setNotifications(await response.json());
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
  } catch (error) {
    setErreur(error.message);
  }
}

  async function chargerProfil(accessToken) {
    const response = await apiFetch(`${API_URL}/auth/me/`, {}, accessToken);

    if (response.ok) {
      const donnees = await response.json();
      setRole(donnees.role);
    }
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
        throw new Error("Nom d'utilisateur ou mot de passe incorrect.");
      }

      localStorage.setItem("access_token", donnees.access);
      setToken(donnees.access);
      await chargerProfil(donnees.access);
      setPassword("");
      await chargerCourriers(donnees.access);
await chargerNotifications(donnees.access);
    } catch (error) {
      setErreur(error.message);
      setChargement(false);
    }
  }

  async function executerAction(courrierId, action, texteSucces) {
    setErreur("");
    setMessage("");
  
    try {
      const response = await apiFetch(
        `${API_URL}/courriers/${courrierId}/${action}/`,
        { method: "POST" }
      );
  
      const resultat = await response.json();
  
      if (!response.ok) {
        throw new Error(resultat.detail || "Action impossible.");
      }
  
      setMessage(texteSucces);
      await chargerCourriers(token);
    } catch (error) {
      setErreur(error.message);
    }
  }

  async function changerStatut(courrier, statut, texteSucces) {
    setErreur("");
    setMessage("");

    try {
      const response = await apiFetch(
        `${API_URL}/courriers/${courrier.id}/changer-statut/`,
        {
          method: "POST",
          body: JSON.stringify({ statut }),
        }
      );
      const resultat = await response.json();

      if (!response.ok) {
        throw new Error(resultat.detail || "Changement de statut impossible.");
      }

      setMessage(texteSucces);
      await chargerCourriers(token);
    } catch (error) {
      setErreur(error.message);
    }
  }
async function ouvrirAffectation(courrier) {
  setErreur("");
  setCourrierAAffecter(courrier);
  setAffectation({
    serviceId: "",
    utilisateurId: "",
    commentaire: "",
  });

  try {
    const [servicesResponse, utilisateursResponse] = await Promise.all([
      apiFetch(`${API_URL}/services/`),
      apiFetch(`${API_URL}/utilisateurs/`),
    ]);

    if (!servicesResponse.ok || !utilisateursResponse.ok) {
      throw new Error("Impossible de charger les services ou utilisateurs.");
    }

    setServices(await servicesResponse.json());
    setUtilisateurs(await utilisateursResponse.json());
  } catch (error) {
    setErreur(error.message);
  }
}

function modifierAffectation(event) {
  setAffectation({
    ...affectation,
    [event.target.name]: event.target.value,
  });
}

async function envoyerAffectation(event) {
  event.preventDefault();

  if (!affectation.serviceId && !affectation.utilisateurId) {
    setErreur("Sélectionnez au moins un service ou un utilisateur.");
    return;
  }

  setErreur("");
  setMessage("");

  const donnees = {
    commentaire: affectation.commentaire,
  };

  if (affectation.serviceId) {
    donnees.service_id = Number(affectation.serviceId);
  }

  if (affectation.utilisateurId) {
    donnees.utilisateur_id = Number(affectation.utilisateurId);
  }

  try {
    const response = await apiFetch(
      `${API_URL}/courriers/${courrierAAffecter.id}/affecter/`,
      {
        method: "POST",
        body: JSON.stringify(donnees),
      }
    );

    const resultat = await response.json();

    if (!response.ok) {
      throw new Error(resultat.detail || "Affectation impossible.");
    }

    setMessage("Courrier affecté avec succès.");
    setCourrierAAffecter(null);
    await chargerCourriers(token);
  } catch (error) {
    setErreur(error.message);
  }
}

  function seDeconnecter() {
    localStorage.removeItem("access_token");
    setToken("");
    setRole("");
    setCourriers([]);
    setUsername("");
    setMessage("");
setNotifications([]);
setAfficherNotifications(false);
  }

  useEffect(() => {
    const tokenSauvegarde = localStorage.getItem("access_token");
  
    if (!tokenSauvegarde) {
      return;
    }
  
    async function restaurerSession() {
      try {
        const profilResponse = await fetch(`${API_URL}/auth/me/`, {
          headers: {
            Authorization: `Bearer ${tokenSauvegarde}`,
          },
        });
  
        if (!profilResponse.ok) {
          localStorage.removeItem("access_token");
          return;
        }
  
        const profil = await profilResponse.json();
  
        setToken(tokenSauvegarde);
        setRole(profil.role);
  
        const courriersResponse = await fetch(`${API_URL}/courriers/`, {
          headers: {
            Authorization: `Bearer ${tokenSauvegarde}`,
          },
        });
  
        if (!courriersResponse.ok) {
          throw new Error("Impossible de charger les courriers.");
        }
  
        setCourriers(await courriersResponse.json());

        const notificationsResponse = await fetch(`${API_URL}/notifications/`, {
          headers: {
            Authorization: `Bearer ${tokenSauvegarde}`,
          },
        });

        if (!notificationsResponse.ok) {
          throw new Error("Impossible de charger les notifications.");
        }

        setNotifications(await notificationsResponse.json());
      } catch (error) {
        localStorage.removeItem("access_token");
        setErreur(error.message);
      }
    }
  
    restaurerSession();
  }, []);

  if (!token) {
    return (
      <main className="conteneur connexion">
        <section className="carte">
          <h1>Gestion des courriers</h1>
          <p>Connectez-vous pour accéder à l’application.</p>

          <form onSubmit={seConnecter}>
            <label htmlFor="username">Nom d’utilisateur</label>
            <input
              id="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />

            <label htmlFor="password">Mot de passe</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />

            {erreur && <p className="erreur">{erreur}</p>}

            <button type="submit" disabled={chargement}>
              {chargement ? "Connexion..." : "Se connecter"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="conteneur">
      <header className="entete">
        <div>
          <h1>Tableau de bord</h1>
          <p>Liste des courriers enregistrés</p>
        </div>

        <div className="actions">
          <button
            className="bouton-notification"
            onClick={() => setAfficherNotifications(!afficherNotifications)}
          >
            Notifications ({notifications.filter((notification) => !notification.lu).length})
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
    <h2>Mes notifications</h2>

    {notifications.length === 0 ? (
      <p>Aucune notification.</p>
    ) : (
      notifications.map((notification) => (
        <article
          key={notification.id}
          className={`notification ${notification.lu ? "lue" : "non-lue"}`}
        >
          <div>
            <strong>{notification.type.toUpperCase()}</strong>
            <p>{notification.message}</p>

            {notification.courrier_numero && (
              <small>Courrier : {notification.courrier_numero}</small>
            )}
          </div>

          {!notification.lu && (
            <button
              className="petit-bouton"
              onClick={() => marquerNotificationLue(notification.id)}
            >
              Marquer comme lue
            </button>
          )}
        </article>
      ))
    )}
  </section>
)}
{courrierAAffecter && (
  <section className="carte formulaire">
    <h2>Affecter {courrierAAffecter.numero}</h2>

    <form onSubmit={envoyerAffectation}>
      <div className="grille">
        <div>
          <label htmlFor="serviceId">Service</label>
          <select
            id="serviceId"
            name="serviceId"
            value={affectation.serviceId}
            onChange={modifierAffectation}
          >
            <option value="">-- Choisir un service --</option>
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.code} - {service.nom}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="utilisateurId">Utilisateur</label>
          <select
            id="utilisateurId"
            name="utilisateurId"
            value={affectation.utilisateurId}
            onChange={modifierAffectation}
          >
            <option value="">-- Choisir un utilisateur --</option>
            {utilisateurs.map((utilisateur) => (
              <option key={utilisateur.id} value={utilisateur.id}>
                {utilisateur.username} ({utilisateur.role})
              </option>
            ))}
          </select>
        </div>
      </div>

      <label htmlFor="commentaire">Commentaire</label>
      <textarea
        id="commentaire"
        name="commentaire"
        value={affectation.commentaire}
        onChange={modifierAffectation}
        rows="3"
      />

<div className="actions">
  <button type="submit" disabled={chargement}>
    {chargement ? "Affectation..." : "Confirmer l’affectation"}
  </button>

  <button
    type="button"
    className="bouton-secondaire"
    onClick={() => setCourrierAAffecter(null)}
  >
    Annuler
  </button>
</div>
    </form>
  </section>
)}

      <section className="carte">
        <h2>Courriers</h2>

        {chargement ? (
          <p>Chargement des courriers...</p>
        ) : courriers.length === 0 ? (
          <p>Aucun courrier enregistré.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Numéro</th>
                <th>Type</th>
                <th>Objet</th>
                <th>Priorité</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
  {courriers.map((courrier) => (
    <tr key={courrier.id}>
      <td>{courrier.numero}</td>
      <td>{courrier.type_courrier}</td>
      <td>{courrier.objet}</td>
      <td>{courrier.priorite}</td>
      <td>{libellesStatut[courrier.statut] || courrier.statut}</td>

      <td>
        {courrier.type_courrier === "sortant" &&
          courrier.statut === "brouillon" && (
            <button
              className="petit-bouton"
              onClick={() =>
                executerAction(
                  courrier.id,
                  "soumettre_validation",
                  "Courrier soumis pour validation."
                )
              }
            >
              Soumettre
            </button>
            )}

        {courrier.type_courrier === "sortant" &&
          courrier.statut === "valide" && (
            <button
              className="petit-bouton"
              onClick={() =>
                changerStatut(courrier, "envoye", "Courrier envoyé avec succès.")
              }
            >
              Marquer envoyé
            </button>
          )}

        {courrier.type_courrier === "sortant" &&
          courrier.statut === "envoye" && (
            <button
              className="petit-bouton"
              onClick={() =>
                changerStatut(courrier, "archive", "Courrier archivé avec succès.")
              }
            >
              Archiver
            </button>
          )}

        {courrier.type_courrier === "entrant" &&
          ["recu", "affecte", "en_attente"].includes(courrier.statut) && (
            <button
              className="petit-bouton"
              onClick={() =>
                changerStatut(
                  courrier,
                  "en_cours",
                  "Courrier mis en cours de traitement."
                )
              }
            >
              {courrier.statut === "en_attente" ? "Reprendre" : "Démarrer"}
            </button>
          )}

        {courrier.type_courrier === "entrant" &&
          courrier.statut === "en_cours" && (
            <>
              <button
                className="petit-bouton"
                onClick={() =>
                  changerStatut(
                    courrier,
                    "en_attente",
                    "Courrier mis en attente."
                  )
                }
              >
                Mettre en attente
              </button>
              <button
                className="petit-bouton"
                onClick={() =>
                  changerStatut(courrier, "traite", "Courrier marqué comme traité.")
                }
              >
                Marquer traité
              </button>
            </>
          )}

        {courrier.type_courrier === "entrant" &&
          courrier.statut === "traite" && (
            <button
              className="petit-bouton"
              onClick={() =>
                changerStatut(courrier, "archive", "Courrier archivé avec succès.")
              }
            >
              Archiver
            </button>
          )}

        {courrier.type_courrier === "sortant" &&
          courrier.statut === "en_validation" &&
          (role === "admin" || role === "responsable") && (
            <button
              className="petit-bouton"
              onClick={() =>
                executerAction(
                  courrier.id,
                  "valider",
                  "Courrier validé avec succès."
                )
              }
            >
              Valider
            </button>
          )}

        {courrier.type_courrier === "entrant" &&
          !["traite", "archive"].includes(courrier.statut) && (
            <button
              className="petit-bouton"
              onClick={() => ouvrirAffectation(courrier)}
            >
              Affecter
            </button>
          )}
      </td>
    </tr>
  ))}
</tbody>
          </table>
        )}
      </section>
    </main>
  );
}

export default App;
