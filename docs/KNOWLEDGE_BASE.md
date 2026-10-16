# Where the Solution Mapper's knowledge lives

The AI never answers from its own memory. Every answer is built from three
sources of Terragni knowledge:

| # | Source | Where | What it holds |
| --- | --- | --- | --- |
| 1 | **Oracle database** (main knowledge base) | Oracle server (settings in `backend/.env`) | Terragni's documents split into searchable parts, plus case studies, services, methods, industries, problems and results |
| 2 | **Company profile** | `backend/data/company_profile.md` | Facts about Terragni itself: who it is, beliefs, approach, brand colours, logo, font, name meaning, contact details |
| 3 | **Legacy files** (older version) | `backend/data/terragni_kb.json`, `backend/data/case_studies/*.md` | Original taxonomy and 2 case-study write-ups; used only by the case-study detail link and the test questions |

## 1. How documents get into Oracle (the knowledge pipeline)

```
backend/data1/raw/pdf, raw/pptx      <- you drop Terragni PDFs / PowerPoints here
        │
        ▼  backend/ingestion/pipeline.py       read the file (pypdf / python-pptx),
        │  backend/ingestion/chunker.py         clean the text, split into sections and chunks
        ▼
backend/data1/processed/*.json        <- one JSON per document (text, sections, chunks)
        │
        ▼  backend/database/oracle_loader.py   save DOCUMENT, DOCUMENT_SECTION, DOCUMENT_CHUNK
        ▼  backend/embeddings/ollama_embeddings.py
        │                                       turn each chunk into "search numbers" (embeddings)
        │                                       with Ollama nomic-embed-text -> DOCUMENT_CHUNK_EMBEDDING
        ▼  backend/knowledge/extractor.py       Groq reads each document and extracts case studies,
        │                                       services, methods, industries, problems, results
        │                                       -> KNOWLEDGE_EXTRACTION_STAGING (for review)
        ▼  backend/knowledge/promoter.py        moves approved items into the master tables
                                                CASE_STUDY, OFFERING, FRAMEWORK, INDUSTRY,
                                                CHALLENGE, OUTCOME and their link tables
                                                (CASE_STUDY_EVIDENCE links a case study to its chunks)
```

`backend/run_knowledge_pipeline.py` runs the extractor and promoter for every
document in Oracle and writes logs to `backend/knowledge_pipeline_logs/`.

### Oracle tables

| Table | Meaning |
| --- | --- |
| `DOCUMENT` | One row per PDF / PowerPoint (37 today) |
| `DOCUMENT_SECTION` | Sections of each document |
| `DOCUMENT_CHUNK` | Small searchable text parts (803 today) |
| `DOCUMENT_CHUNK_EMBEDDING` | The "search numbers" for each chunk |
| `CASE_STUDY` | Each Terragni project: challenge, approach, solution, outcome |
| `CASE_STUDY_EVIDENCE` | Which chunks prove which case study |
| `OFFERING`, `FRAMEWORK`, `INDUSTRY`, `CHALLENGE`, `OUTCOME` | Services, methods, industries, problem types, results |
| `CASE_STUDY_OFFERING`, `CASE_STUDY_FRAMEWORK`, … | Links between case studies and the above |

## 2. How a question is answered (runtime)

```
Browser  ──POST /api/ask──►  backend/app/app.py
                                │  confidentiality.py  hide private details
                                │  journey/intent.py   challenge, knowledge or mixed?
                                ▼
            ┌───────────────────┴────────────────────┐
   Challenge path                              Knowledge path
   journey_service.run_journey()               journey/knowledge.py
            │                                          │
            └──► retrieval/journey_retrieval.py ◄──────┘
                   └─ retrieval/semantic_search.py
                        1. turn the question into search numbers (Ollama)
                        2. compare with all 803 chunk embeddings (kept in memory)
                        3. return the closest chunks + their case studies
            │                                          │  + company_profile.md (always)
            ▼                                          ▼
     Groq writes the answer using ONLY this evidence (JSON)
            │
            ▼  every service / method / case study the AI names is checked
               against the evidence; client names are removed
     Browser renders the result page (app.js + mapper-visuals.js)
```

Key code:

- `backend/retrieval/semantic_search.py` – loads the embeddings from Oracle
  once (cached 15 minutes), compares them with the question by cosine
  similarity, and links untagged chunks to their document's case study.
- `backend/retrieval/journey_retrieval.py` – groups the best chunks into case
  studies and attaches their services, methods, industries and results.
- `backend/journey_service.py` – Challenge path: sends the evidence to Groq
  and checks the answer.
- `backend/journey/knowledge.py` – Knowledge path: adds brochures, the full
  service/method catalogue and the company profile, then asks Groq.
- `backend/app/confidentiality.py` – hides private details and client names.

## 3. How to add or change knowledge

- **New case study or brochure:** put the PDF/PPTX in `backend/data1/raw/pdf`
  or `raw/pptx`, run the ingestion, embeddings and knowledge pipeline, then
  restart the server.
- **Company facts** (brand, contact, values…): edit
  `backend/data/company_profile.md`. No restart needed; it reloads when saved.
