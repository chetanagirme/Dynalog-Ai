@echo off
title Dynalog AI Server
echo Starting Ollama AI engine...
start "Ollama" cmd /k "ollama serve"
timeout /t 3 /nobreak > nul
echo Starting Dynalog AI chatbot...
cd C:\Users\Admin\Dynalog-chat
call venv\Scripts\activate
echo.
echo ================================
echo  Dynalog AI is running!
echo  Open: http://localhost:8080
echo ================================
python app.py