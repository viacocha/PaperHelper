# PaperHelper

PaperHelper is a local web tool for reviewing `信息系统项目管理师` essays in `.docx` format.

## Structure

- `backend`: Flask service for parsing DOCX essays, scoring against built-in standards, and generating a suggestion report DOCX.
- `frontend`: React + Vite interface for upload, scoring view, and report download.
- `docs`: project notes.

## Current status

V1 scaffold includes:

- essay standards for selected knowledge areas and performance domains
- DOCX parsing and scoring pipeline
- suggestion report generation
- upload/result UI

## Run

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend:

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 -m app.main
```

API runs at `http://127.0.0.1:8000`.
