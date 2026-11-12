# INFO698 Publications Exploration

An interactive literature exploration project for publications at the intersection
of AI, data science, and healthcare. It collects publication metadata from
OpenAlex and Semantic Scholar, supports semantic publication search, and builds
a publication-centered knowledge graph for concept-based exploration.

## Author

- **Cesar Castro M.**
- [LinkedIn](https://www.linkedin.com/in/cesargcm/)
- University of Arizona, College of Information Science
- Capstone Project — Fall 2026

## AI-Assisted Development

GitHub Copilot (autocomplete and conversational agents) assisted with code
implementation and debugging, including code generation, syntax completion,
architectural clarification, and troubleshooting. Copilot also helped draft
code documentation and docstrings. The author reviewed, edited, and validated
these contributions for technical accuracy and remains responsible for the
project's final code and documentation.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL with pgvector (the project is configured for Neon)
- OpenAI API key for semantic search and embedding/loading
- OpenAlex API key and contact email for OpenAlex collection
- Semantic Scholar API key is optional

## Setup

See the [Installation Guide](Docs/Installation%20Guide.md) for setup
instructions.

## Run the application

```powershell
uv run streamlit run src\stapp\app.py
```

The current navigation contains:

- **Home** — collection counts, date range, and a publication example.
- **Search** — semantic publication search and selected-publication details.
- **Explorer** — concept-based graph search and publication relationship views.
- **AI Assistant** — literature chat with topic screening, follow-up questions,
  abstract-grounded answers, and linked publication citations.

## Run publication ingestion

The separate pipeline interface collects and processes publications:

```powershell
uv run streamlit run src\Ingest_Publications\data_pipeline_ui.py
```

It can search OpenAlex and Semantic Scholar, ingest publication vectors, extract
graphs with GLiNER, and embed/load graph data. The stages can also be run
individually; see the pipeline documentation for prerequisites and restart
behavior.

## Docker

Build and run the Streamlit application with credentials supplied at runtime:

```powershell
docker build -t info698-litexplore .
docker run --rm -p 8000:8000 --env-file prod.env info698-litexplore
```

## Documentation

- [Installation Guide](Docs/Installation%20Guide.md) — step-by-step Windows
  setup for a new PC.
- [AI Assistant Workflow](Docs/AI%20Assistant%20Workflow.md) — LangGraph flow
  diagram, question handling, citations, setup, and limitations.
- [Publication Data Pipeline](Docs/Publication%20Data%20Pipeline.md) — retrieval,
  normalization, ingestion, graph construction, database behavior, and evaluation
  limits.
- [Knowledge Graph Approach](Docs/Knowledge%20Graph%20Approach.md) — graph
  extraction, identifiers, relationships, and loading.
- [GLiNER Extraction Pipeline](Docs/GLiNER%20Extraction%20Pipeline.md) — detailed
  extraction behavior and JSONL output.

For environment variable details, see [.env.example](.env.example). Keep
generated publication and graph data under `src/` separate from source code and
never commit secrets or private credentials.
