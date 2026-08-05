import { useEffect, useState } from "react";

const API_URL = "http://127.0.0.1:8000/api";

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [courriers, setCourriers] = useState([]);
  const [erreur, setErreur] = useState("");
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

      const donnees = await response.json();
      setCourriers(donnees);
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
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username,
          password,
        }),
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

  function seDeconnecter() {
    localStorage.removeItem("access_token");
    setToken("");
    setCourriers([]);
    setUsername("");
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
              type="text"
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

        <button className="bouton-secondaire" onClick={seDeconnecter}>
          Se déconnecter
        </button>
      </header>

      {erreur && <p className="erreur">{erreur}</p>}

      {chargement ? (
        <p>Chargement des courriers...</p>
      ) : (
        <section className="carte">
          <h2>Courriers</h2>

          {courriers.length === 0 ? (
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
      )}
    </main>
  );
}

export default App;