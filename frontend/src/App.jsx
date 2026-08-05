import { useEffect, useState } from "react";

const API_URL = "/api";

const formulaireInitial = {
  typeCourrier: "entrant",
  objet: "",
  expediteur: "",
  destinataire: "",
  categorie: "Administratif",
  priorite: "normal",
  description: "",
  dateReception: "",
  dateEcheance: "",
};

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [courriers, setCourriers] = useState([]);
  const [formulaire, setFormulaire] = useState(formulaireInitial);
  const [afficherFormulaire, setAfficherFormulaire] = useState(false);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [chargement, setChargement] = useState(false);

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
    } catch (error) {
      setErreur(error.message);
      setChargement(false);
    }
  }

  async function creerCourrier(event) {
    event.preventDefault();
    setErreur("");
    setMessage("");
    setChargement(true);

    const donnees = {
      type_courrier: formulaire.typeCourrier,
      objet: formulaire.objet,
      expediteur: formulaire.expediteur,
      destinataire: formulaire.destinataire,
      categorie: formulaire.categorie,
      priorite: formulaire.priorite,
      description: formulaire.description,
    };

    if (formulaire.dateReception) {
      donnees.date_reception = formulaire.dateReception;
    }

    if (formulaire.dateEcheance) {
      donnees.date_echeance = formulaire.dateEcheance;
    }

    try {
      const response = await apiFetch(`${API_URL}/courriers/`, {
        method: "POST",
        body: JSON.stringify(donnees),
      });

      const resultat = await response.json();

      if (!response.ok) {
        throw new Error(
          resultat.detail || "Impossible de créer le courrier."
        );
      }

      setMessage(`Courrier ${resultat.numero} créé avec succès.`);
      setFormulaire(formulaireInitial);
      setAfficherFormulaire(false);
      await chargerCourriers(token);
    } catch (error) {
      setErreur(error.message);
    } finally {
      setChargement(false);
    }
  }

  function modifierFormulaire(event) {
    setFormulaire({
      ...formulaire,
      [event.target.name]: event.target.value,
    });
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

  function seDeconnecter() {
    localStorage.removeItem("access_token");
    setToken("");
    setRole("");
    setCourriers([]);
    setUsername("");
    setMessage("");
  }

  useEffect(() => {
    const tokenSauvegarde = localStorage.getItem("access_token");

    if (tokenSauvegarde) {
      // Valider le token en appelant /auth/me/ avant de l'utiliser
      fetch(`${API_URL}/auth/me/`, {
        headers: { Authorization: `Bearer ${tokenSauvegarde}` },
      }).then((res) => {
        if (res.ok) {
          return res.json().then((donnees) => {
            setToken(tokenSauvegarde);
            setRole(donnees.role);
            chargerCourriers(tokenSauvegarde);
          });
        } else {
          // Token invalide ou expiré → on nettoie
          localStorage.removeItem("access_token");
        }
      });
    }
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
          <button onClick={() => setAfficherFormulaire(!afficherFormulaire)}>
            {afficherFormulaire ? "Fermer le formulaire" : "Nouveau courrier"}
          </button>

          <button className="bouton-secondaire" onClick={seDeconnecter}>
            Se déconnecter
          </button>
        </div>
      </header>

      {erreur && <p className="erreur">{erreur}</p>}
      {message && <p className="message">{message}</p>}

      {afficherFormulaire && (
        <section className="carte formulaire">
          <h2>
  Nouveau courrier{" "}
  {formulaire.typeCourrier === "entrant" ? "entrant" : "sortant"}
</h2>

          <form onSubmit={creerCourrier}>
            <div className="grille">
            <div>
  <label htmlFor="typeCourrier">Type de courrier *</label>
  <select
    id="typeCourrier"
    name="typeCourrier"
    value={formulaire.typeCourrier}
    onChange={modifierFormulaire}
  >
    <option value="entrant">Courrier entrant</option>
    <option value="sortant">Courrier sortant</option>
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

              {formulaire.typeCourrier === "entrant" ? (
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
                <label htmlFor="categorie">Catégorie *</label>
                <input
                  id="categorie"
                  name="categorie"
                  value={formulaire.categorie}
                  onChange={modifierFormulaire}
                  required
                />
              </div>

              <div>
                <label htmlFor="priorite">Priorité *</label>
                <select
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
                <label htmlFor="dateReception">Date de réception</label>
                <input
                  id="dateReception"
                  name="dateReception"
                  type="date"
                  value={formulaire.dateReception}
                  onChange={modifierFormulaire}
                />
              </div>

              <div>
                <label htmlFor="dateEcheance">Date d’échéance</label>
                <input
                  id="dateEcheance"
                  name="dateEcheance"
                  type="date"
                  value={formulaire.dateEcheance}
                  onChange={modifierFormulaire}
                />
              </div>
            </div>

            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              name="description"
              value={formulaire.description}
              onChange={modifierFormulaire}
              rows="4"
            />

            <button type="submit" disabled={chargement}>
              {chargement ? "Enregistrement..." : "Créer le courrier"}
            </button>
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
                  <td>{courrier.statut}</td>
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