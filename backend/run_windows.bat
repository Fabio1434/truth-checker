@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Truth Checker - demarrage
echo ============================================

if not exist ".env" (
    echo.
    echo [ATTENTION] Aucun fichier .env trouve.
    echo Copie de .env.example vers .env ...
    copy .env.example .env >nul
    echo.
    echo ^>^>^> Ouvrez backend\.env et collez votre cle GEMINI_API_KEY,
    echo ^>^>^> puis relancez ce script.
    echo.
    notepad .env
    pause
    exit /b 1
)

if not exist "venv" (
    echo Creation de l'environnement virtuel...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Mise a jour de pip...
python -m pip install --upgrade pip -q

echo Installation des dependances...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERREUR] L'installation des dependances a echoue. Verifiez le message
    echo ci-dessus ^(souvent : version de Python trop recente/ancienne^).
    echo Essayez avec Python 3.11 ou 3.12 si le probleme persiste.
    echo.
    pause
    exit /b 1
)

echo.
echo Lancement du serveur sur http://localhost:8000
echo (laissez cette fenetre ouverte pendant la demo)
echo.

start "" http://localhost:8000
python -m uvicorn main:app --host 0.0.0.0 --port 8000

pause
