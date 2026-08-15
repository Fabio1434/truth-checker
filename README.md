# Truth Checker

**Vérifiez l'information. Retrouvez la vérité.**

Truth Checker est un outil de vérification factuelle en temps réel : on lui soumet un **texte**,
une **URL d'article**, ou une **image** (capture d'écran, publication, affiche...), et il
interroge le web mondial en direct — agences de presse, sources officielles, sites de
vérification des faits, littérature scientifique — pour rendre un **score de fiabilité**, une
**explication claire**, la **liste exacte des sources trouvées**, et, si l'information est
fausse ou trompeuse, **ce que disent réellement les faits**.

Réalisé pour le **Hackathon Jeunesse 2026 de l'UNESCO** — *« Faites votre part : les jeunes
façonnent l'avenir de l'éducation aux médias et à l'information (EMI) »*.

---

## Pourquoi ce projet

La désinformation ne se limite pas aux fausses nouvelles : elle inclut les images sorties de
leur contexte, les statistiques déformées, les captures d'écran truquées, les rumeurs de santé
partagées sur WhatsApp. Les jeunes sont à la fois les premières victimes de ces contenus et les
mieux placés pour construire les outils qui y répondent — c'est exactement le mandat du thème EMI
de l'UNESCO.

Truth Checker ne se contente pas de dire « vrai » ou « faux » : il **montre son travail**. Chaque
verdict est accompagné des sources réelles, avec leur position (confirme / contredit / apporte du
contexte), pour que l'utilisateur puisse vérifier par lui-même — l'objectif est d'apprendre à
vérifier, pas de remplacer l'esprit critique par une boîte noire.

## Comment ça marche

```
 ┌──────────────┐      ┌──────────────────────────────────────────┐      ┌───────────────┐
 │   Frontend   │ ───▶ │                 Backend                   │ ───▶ │   Réponse     │
 │ texte/URL/   │      │  FastAPI reçoit le contenu et appelle      │      │  structurée   │
 │ image        │      │  l'API Groq Compound + vision       │      │  (JSON/SSE)   │
 └──────────────┘      │   • Web Search / Visit Website → vérifie   │      │  score,       │
                        │     des sources en temps réel              │      │  verdict,     │
                        │   • Vision → lit les images avant         │      │  explication, │
                        │     si une URL est fournie                │      │  sources,     │
                        │  Groq compare les sources, détecte les  │      │  correction,  │
                        │  contradictions et rédige un verdict      │      │  sous-scores  │
                        └──────────────────────────────────────────┘      └───────────────┘
```

1. **Le frontend** envoie le contenu à `POST /api/analyze/stream` (ou `/api/analyze` en repli
   automatique si le streaming échoue).
2. **Le backend** utilise Groq Compound (`groq/compound`) pour la vérification texte/URL.
   Compound dispose d'une recherche web et d'une visite de sites intégrées qui récupèrent des
   informations en temps réel. Pour les images, un modèle vision Groq extrait d'abord le contenu
   visible, puis Compound vérifie les affirmations sur le web.
3. Groq renvoie un objet JSON structuré : affirmations, résumé, sources, contexte et correction.
   Le backend recalcule ensuite le score final avec l'Evidence Engine et **n'accepte que les
   URLs réellement retournées par les outils web de Groq**.
4. **Le frontend** affiche le résultat sous forme de « dossier » : jauge de score, tampon de
   verdict, barres de sous-scores, et piste de preuves filtrable par position (confirme /
   contredit / contexte).

Aucune donnée n'est fabriquée côté backend : chaque source affichée à l'écran est une URL que
l'outil `web_search`/`web_fetch` a réellement retournée pendant l'appel API.

## Fonctionnalités de l'interface

- **Progression de recherche** : le backend envoie au frontend les requêtes de recherche et l'étape
  de verdict après la réponse Groq. Le endpoint SSE est conservé pour la compatibilité frontend,
  mais Groq Compound effectue la recherche serveur dans un appel principal.
- **Sous-scores de confiance** : trois barres (fiabilité des sources, corroboration, consensus)
  détaillent comment le score global a été obtenu.
- **Filtre des preuves** : basculer entre toutes les sources, celles qui confirment, celles qui
  contredisent, et celles qui apportent du contexte.
- **Historique local** : les derniers dossiers consultés sont sauvegardés dans le navigateur
  (`localStorage`, rien n'est envoyé à un serveur tiers) et réaffichables en un clic.
- **Exemples rapides** : quatre affirmations prêtes à tester pour une démo instantanée.
- **Copier le dossier** : copie un résumé texte complet (verdict, score, explication, sources)
  dans le presse-papier — pratique pour partager un résultat.
- **Coller depuis le presse-papier** et **raccourci clavier** `Ctrl`/`Cmd`+`Entrée` pour analyser
  sans quitter le clavier.
- **Ambiance visuelle réactive** : le fond de page se teinte légèrement selon le verdict obtenu.

## Structure du projet

```
truthchecker/
├── frontend/
│   ├── index.html        interface (formulaire + dossier de résultats)
│   ├── styles.css         design "salle de rédaction / dossier d'enquête"
│   └── app.js              logique : onglets, upload image, appel API, rendu
├── backend/
│   ├── main.py             API FastAPI + appel à Groq (web_search + web_fetch)
│   ├── requirements.txt
│   ├── .env.example
│   ├── run_windows.bat     lance tout en un clic (Windows)
│   └── run_unix.sh         équivalent macOS/Linux
└── README.md
```

## Installation

### Prérequis
- Python 3.10+
- Une clé API Groq : https://console.groq.com/keys

### Windows (le plus simple)
1. Double-cliquez sur `backend/run_windows.bat`.
2. Au premier lancement, un fichier `.env` s'ouvre : collez votre `GROQ_API_KEY`, enregistrez,
   relancez le script.
3. Le navigateur s'ouvre automatiquement sur `http://localhost:8000`.

### macOS / Linux
```bash
cd backend
cp .env.example .env        # puis collez votre clé dans .env
./run_unix.sh
```

### Manuel (n'importe quel OS)
```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # puis éditez .env avec votre clé
uvicorn main:app --reload
```
Ouvrez ensuite `http://localhost:8000` — le backend sert aussi le frontend.

> Le frontend fonctionne aussi ouvert directement en fichier local (`frontend/index.html`) tant
> que le backend tourne sur `localhost:8000` (voir `API_BASE` en haut de `app.js`).

## API

### `POST /api/analyze/stream` (recommandé)
Mêmes paramètres que `/api/analyze` ci-dessous, mais répond en **Server-Sent Events** avec des
événements intermédiaires (`step`, `search`, `fetch`) suivis d'un événement final `result`
contenant le même objet JSON que `/api/analyze`, ou `error` en cas d'échec.

### `POST /api/analyze`

```jsonc
// texte
{ "type": "text", "content": "Boire de l'eau citronnée élimine les toxines.", "language": "fr" }

// URL
{ "type": "url", "content": "https://exemple.com/article", "language": "fr" }

// image (base64 sans le préfixe data:)
{ "type": "image", "image_base64": "...", "image_media_type": "image/jpeg", "content": "contexte optionnel" }
```

Réponse :
```jsonc
{
  "verdict": "faux",
  "score": 12,
  "headline_claim": "...",
  "summary": "...",
  "explanation": "...",
  "correction": "...",
  "confidence_breakdown": { "source_reliability": 20, "corroboration": 10, "consensus": 15 },
  "sources": [
    { "title": "...", "url": "...", "domain": "...", "stance": "contredit", "excerpt": "..." }
  ],
  "queries": ["...", "..."],
  "searches_performed": 4,
  "elapsed_ms": 8213
}
```

### `GET /api/health`
Vérifie que le serveur tourne et qu'une clé API est bien configurée.

## Limites & éthique (assumées volontairement)

- Truth Checker est une **aide à la vérification**, pas un tribunal de la vérité absolue : les
  scores et verdicts dépendent de la qualité des sources disponibles en ligne au moment de la
  recherche.
- Sur des sujets très récents ou très locaux, peu de sources fiables peuvent exister : le verdict
  `non_verifiable` est utilisé plutôt que de forcer une réponse.
- Le raisonnement interne du modèle n'est pas exposé (pour éviter le bruit et les manipulations de
  prompt) — seul le résultat vérifiable (sources + citations) est montré, dans l'esprit d'un
  raisonnement traçable plutôt qu'une boîte noire.
- Aucune clé API n'est exposée côté client : tous les appels passent par le backend.

## Pistes d'évolution

- Historique des vérifications + partage d'un dossier via lien court.
- Extension navigateur pour vérifier un post en un clic depuis les réseaux sociaux.
- Support du malgache et d'autres langues locales pour l'EMI hors des zones francophones/anglophones.
- Détection d'images générées par IA / retouchées (métadonnées, recherche d'image inversée).
- Mode « classe » pour les enseignants : générer des exercices d'EMI à partir d'un dossier vérifié.

---

*Ce projet répond à l'appel de l'UNESCO : « Faites votre part : les jeunes façonnent l'avenir de
l'éducation aux médias et à l'information ».*

## Truth Lab — nouvelles fonctionnalités

### Truth Passport
Le Passport est stocké localement dans le navigateur. Il récapitule les vérifications, les sources consultées, les challenges et les badges EMI.

### Challenge Amis
Après une vérification, le bouton « Créer un challenge » transforme l'affirmation en mini-défi. L'utilisateur choisit d'abord son verdict, puis découvre le verdict fondé sur les preuves. Le lien du défi peut être copié et partagé.

### Mode Jury
Le bouton « Mode Jury » masque les éléments secondaires et recentre l'écran sur l'enquête et le dossier de preuves pour une démonstration publique.

### API d'observabilité
- `GET /api/health` — état du moteur, cache et fonctionnalités.
- `GET /api/cache/stats` — statistiques du cache mémoire.
- `DELETE /api/cache` — purge du cache (usage administrateur/local).

### Principe de score
Le score final affiché est un **Evidence Score** calculé par le backend à partir des sources et de leurs caractéristiques. Il n'est pas accepté directement depuis le LLM.

## Authentification multi-utilisateurs (V6.1 → V6.1 Secure)

La version modifiée inclut une authentification centralisée :

- inscription et connexion par email + mot de passe ;
- mot de passe stocké sous forme de hash `scrypt` ;
- jeton de session signé côté serveur ;
- toutes les routes `/api/analyze` et `/api/analyze/stream` nécessitent une session ;
- SQLite stocke les comptes et l'historique des analyses ;
- quota gratuit configurable (`TRUTHCHECKER_DAILY_LIMIT`, 20 par défaut) ;
- la clé `GROQ_API_KEY` reste uniquement dans le backend ;
- aucune clé Groq n'est exposée au navigateur.

### Configuration

Copier `backend/.env.example` vers `backend/.env`, puis définir `GROQ_API_KEY` et surtout un `AUTH_SECRET` long et aléatoire en production.

Le navigateur ne reçoit qu'un jeton de session TruthChecker. L'utilisateur n'a pas besoin de fournir une clé API Groq.
