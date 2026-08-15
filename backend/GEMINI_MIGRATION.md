# Migration vers Google Gemini

Le backend utilise maintenant le SDK officiel `google-genai` et Gemini 2.5 Flash.

## Configuration

1. Créer une clé dans Google AI Studio.
2. Copier `backend/.env.example` vers `backend/.env`.
3. Renseigner `GEMINI_API_KEY`.
4. Installer les dépendances :

```powershell
python -m pip install -r backend/requirements.txt
```

Le moteur utilise :
- Google Search grounding pour les recherches web en temps réel ;
- URL Context pour analyser directement les URL fournies ;
- Gemini multimodal pour les images ;
- Evidence Engine pour calculer le score final de manière déterministe.

Aucune clé API Gemini n'est envoyée au navigateur.
