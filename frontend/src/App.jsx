import { useEffect, useState } from "react";

const API_URL = "http://127.0.0.1:8000/api";

const formulaireInitial = {
  objet: "",
  expediteur: "",
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
  const [courriers, setCourriers] = useState([]);
  const [formulaire, setFormulaire] = useState(formulaireInitial);
  const [afficherFormulaire, setAfficherFormulaire] = useState(false);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [chargement, setChargement] = useState(false);

  async function chargerCourriers(accessToken) {
    setChargement(true);
    setErreur("");

    try {
      const response = await fetch(`${API_URL}/courriers/`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

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
      type_courrier: "entrant",
      objet: formulaire.objet,
      expediteur: formulaire.expediteur,
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
      const response = await fetch(`${API_URL}/courriers/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
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

  function seDeconnecter() {
    localStorage.removeItem("access_token");
    setToken("");
    setCourriers([]);
    setUsername("");
    setMessage("");
  }

  useEffect(() => {
    const tokenSauvegarde = localStorage.getItem("access_token");

    if (tokenSauvegarde) {
      setToken(tokenSauvegarde);
      chargerCourriers(tokenSauvegarde);
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
          <h2>Nouveau courrier entrant</h2>

          <form onSubmit={creerCourrier}>
            <div className="grille">
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
                <label htmlFor="expediteur">Expéditeur *</label>
                <input
                  id="expediteur"
                  name="expediteur"
                  value={formulaire.expediteur}
                  onChange={modifierFormulaire}
                  required
                />
              </div>

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