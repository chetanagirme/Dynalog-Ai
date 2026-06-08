# Dynalog AI — Project Intelligence System

A full-stack AI-powered internal knowledge management system built 
for a defence electronics organisation. Features RAG-based document 
search, streaming AI chat, and automated document generation.

## Features
- NotebookLM-style 3-panel interface
- RAG document search with source citations
- Streaming AI chat (word by word)
- PowerPoint generator (.pptx)
- Block diagram generator (SVG)
- Flowchart generator
- Mind map generator
- Timeline extractor
- Executive briefing generator
- FAQ generator
- Word report generator (.docx)
- Folder/ZIP upload with auto-indexing
- User authentication system
- 100% local — no cloud dependency

## Tech Stack
Python · Flask · ChromaDB · Ollama · LLaMA3 · RAG · 
SQLite · HTML/CSS/JavaScript · python-pptx · LangChain

## Setup

### Requirements
- Python 3.10+
- Ollama installed (ollama.com)

### Installation
```bash
git clone https://github.com/YOURUSERNAME/dynalog-ai.git
cd dynalog-ai
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
ollama pull llama3
python create_db.py
python app.py
```

### Environment variables
Create a `.env` file:
