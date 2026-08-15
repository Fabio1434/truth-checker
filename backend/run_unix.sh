#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  Truth Checker - démarrage"
echo "============================================"

if [ ! -f ".env" ]; then
  echo
  echo "[ATTENTION] Aucun fichier .env trouvé. Copie de .env.example -> .env"
  cp .env.example .env
  echo ">>> Ouvrez backend/.env et collez au moins une clé"
  echo ">>> (GROQ_API_KEY, GEMINI_API_KEY ou OPENAI_API_KEY),"
  echo ">>> puis relancez ce script."
  exit 1
fi

if [ ! -d "venv" ]; then
  echo "Création de l'environnement virtuel..."
  python3 -m venv venv
fi

source venv/bin/activate
echo "Mise à jour de pip..."
python -m pip install --upgrade pip -q
echo "Installation des dépendances..."
pip install -r requirements.txt

echo
echo "Lancement du serveur sur http://localhost:8000"
echo

( sleep 1.5 && (open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null || true) ) &
python -m uvicorn main:app --host 0.0.0.0 --port 8000
