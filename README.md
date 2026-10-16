# Terragni Solution Mapper — Banking Prototype

A website with AI built in. A visitor gives their **role** and **industry**, then either:

- **Challenge path** — describes a business problem. The AI checks whether Terragni has solved something similar for a bank. Good match → a personalised solution page. Not sure → up to 3 short questions, then it tries again. No match → the visitor is invited to contact Terragni.
- **Knowledge path** — asks about Terragni (services, methods, banking work). The AI answers only from Terragni's own brochures and case studies, and shows its sources.

The AI also reads what the visitor types and picks the right path itself. A question with both parts ("Has Terragni helped banks reduce branch visits? Our customers still queue at branches.") gets an answer first, then an offer to look at the visitor's own problem. Every page ends with a contact form that sends Terragni the visitor's role, industry and problem.

This prototype covers **banking only**. A non-banking challenge gets a polite "not covered yet" page; general questions about Terragni are still answered.

## How it works

```
Browser (frontend/)            Flask server (backend/app/app.py)
  index.html + app.js  ──►  POST /api/ask ──► hide private details (confidentiality.py)
  contact.html + contact.js        │            │
                                   │            ▼
                                   │      decide the path (journey/intent.py)
                                   │       ├─ challenge ─► journey_service.run_journey()
                                   │       └─ knowledge ─► journey/knowledge.py
                                   │                 │
                                   │                 ▼
                                   │      meaning search over Oracle chunks (retrieval/)
                                   │      using Ollama embeddings, then Groq writes the
                                   │      answer from that evidence only
                                   ▼
                          POST /api/lead ─► backend/data/leads/leads.jsonl
```

| Part | File |
| --- | --- |
| Web pages | `frontend/templates/*.html`, `frontend/static/js/app.js`, `contact.js`, `css/` |
| Diagrams and icons (Terragni map, symptom-to-solution flow, how-it-works strip) | `frontend/static/js/mapper-visuals.js`, `css/visuals.css` |
| Server and routes | `backend/app/app.py` |
| Path detection (challenge / knowledge / mixed) and banking check | `backend/journey/intent.py` |
| Knowledge answers | `backend/journey/knowledge.py` |
| Challenge matching | `backend/journey_service.py` |
| Meaning search and caches | `backend/retrieval/semantic_search.py`, `journey_retrieval.py` |
| Privacy (hide details, remove client names) | `backend/app/confidentiality.py` |
| Leads and visit log | `backend/app/leads.py` |
| Tests | `backend/evaluation/` |

## API

| Route | Purpose |
| --- | --- |
| `POST /api/ask` | Main entry point. Body: `industry`, `role`, `text`, `mode` (`challenge` or `knowledge`), optional `force`. Returns `path`: `challenge`, `knowledge` or `out_of_scope`. |
| `POST /api/lead` | Contact form. Body: `name`, `email`, `consent`, optional `organisation`, `phone`, `message`, `context`. |
| `POST /api/query`, `POST /api/query/continue` | Challenge path only (kept for compatibility). |
| `GET /api/health` | Checks Oracle and the AI configuration. |

## Run it locally (Windows)

You need: Python 3.12, access to the Terragni Oracle database, Ollama running with `nomic-embed-text`, and a Groq API key.

1. Install packages (from the project folder):

   ```
   python -m pip install -r backend/requirements.txt
   ```

2. Copy `backend/.env.example` to `backend/.env` and fill in the values.

3. Make sure Ollama is running and has the model:

   ```
   ollama pull nomic-embed-text
   ```

4. Start the website **from the project folder** (not from `backend/app`):

   ```
   python -m backend.app.app
   ```

5. Open http://127.0.0.1:5000 (or the `PORT` in your `.env`).

The server loads the Oracle data into memory in the background when it starts. The very first question can take about 25 seconds; after that answers take about 3–5 seconds.

## Test it

```
python -m backend.evaluation.evaluator              # all three areas
python -m backend.evaluation.evaluator intent       # right path chosen
python -m backend.evaluation.evaluator challenge    # right banking example found
python -m backend.evaluation.evaluator knowledge    # correct answers about Terragni
```

A report is saved to `backend/evaluation/last_report.json`. The tests pause 8 seconds between AI questions to stay under Groq's per-minute limit (set `EVAL_PAUSE_SECONDS` to change this). If you still see "temporarily rate-limited", wait a few minutes and run again.

To check the page design without spending AI calls, open the browser console on the home page and pass a saved `/api/ask` response to `TerragniMapper.preview(response, "the question", "Banking", "Head of Strategy")`.

## Leads and visit log

- `backend/data/leads/leads.jsonl` — one line per contact-form submission, with the visitor's journey context.
- `backend/data/leads/visits.jsonl` — one line per question (role, industry, path, outcome, text with private details hidden). Lines with `"outcome": "no_match"` are the list of problems Terragni has no example for yet.

These files contain personal data. They are git-ignored; do not share them. In production they should move to Oracle or Terragni's CRM.

## Adding documents

New PDFs and PowerPoints go through the knowledge pipeline (`backend/run_knowledge_pipeline.py`), which extracts text, splits it into chunks, creates embeddings and saves everything to Oracle. Restart the server afterwards (or wait 15 minutes) so the in-memory cache reloads.

**Known gap:** the personal-lending case studies (customers switching banks, late interest-rate surprises) are not in Oracle yet, so lending challenges currently get an honest "no match". Loading that document will fix it.

## Security

- Secret keys live only in `backend/.env`. Never commit it or include it in a zip.
- Do not share the `backend/venv/` folder; recreate it with `pip install -r backend/requirements.txt`.
- Two source decks in Oracle (the Kotak "Privy League" and Axis "Burgundy" decks) are marked confidential client proposals. The website never shows client names, but confirm with the clients before their content is used in public answers.

## Knowledge base

See `docs/KNOWLEDGE_BASE.md` for where the knowledge lives, how documents are loaded into Oracle, and how a question is answered. Company facts (brand colours, contact details, values) are in `backend/data/company_profile.md`.
