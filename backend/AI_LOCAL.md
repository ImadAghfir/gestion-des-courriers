# Analyse IA locale des courriers

L'analyse ne transmet aucun document à un service cloud. Le navigateur envoie le
fichier au backend Django, qui exécute les outils installés sur le même serveur.

## Prérequis

1. Installez **Ollama**, démarrez son service local, puis téléchargez un modèle :

   ```powershell
   ollama pull qwen2.5:3b
   ```

3. Installez **Tesseract OCR** avec les données de langue française (`fra`).
4. Pour les PDF, installez aussi **Poppler** et rendez `pdftotext` ainsi que
   `pdftoppm` disponibles dans le `PATH` du serveur.

## Configuration optionnelle

Les valeurs par défaut fonctionnent lorsque les exécutables sont dans le `PATH`.
Vous pouvez les remplacer dans `backend/.env` :

```dotenv
AI_OLLAMA_URL=http://127.0.0.1:11434
AI_OLLAMA_MODEL=qwen2.5:3b
AI_OLLAMA_TIMEOUT=240
AI_TESSERACT_COMMAND=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
AI_PDFTOTEXT_COMMAND=C:\\outils\\poppler\\Library\\bin\\pdftotext.exe
AI_PDFTOPPM_COMMAND=C:\\outils\\poppler\\Library\\bin\\pdftoppm.exe
```

Redémarrez ensuite Django. Dans le formulaire « Enregistrer un courrier »,
sélectionnez un PDF, JPG ou PNG puis cliquez sur « Analyser avec l'IA locale ».
Les champs proposés restent modifiables et ne sont enregistrés qu'après
validation manuelle.
