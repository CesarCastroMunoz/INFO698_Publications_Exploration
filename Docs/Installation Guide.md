# Install INFO698 Publications Exploration on a New Windows PC

This guide sets up the Streamlit application on Windows using PowerShell. It
covers running the existing app against a configured PostgreSQL database. The
database, its schema, and publication data are not created by installing the
app.

## What you need before starting

Have the following ready:

- A Windows PC with internet access.
- Git for Windows.
- Python 3.12 and the `uv` package manager.
- Access to a PostgreSQL database that supports the **pgvector extension**, with
  the application's existing schema and data (the project is configured for
  Neon). A standard PostgreSQL database without pgvector is not sufficient.
- An OpenAI API key. The app uses it to create embeddings for Search and
  Explorer.
- The database connection URL and permission for this PC/network to connect.
- For publication collection only: an OpenAlex API key and contact email.
  Semantic Scholar's API key is optional.

The app's Home page, Search, and Explorer all query the database. Search and
Explorer also call OpenAI. A new, empty database will not contain publications
or graph data to explore.

## Step 1: Install the prerequisites

Install Git for Windows, Python 3.12, and uv from their official sources:

- [Git for Windows](https://git-scm.com/download/win)
- [Python for Windows](https://www.python.org/downloads/windows/) — install a
  Python 3.12 release and enable the Python launcher when prompted.
- [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/)

Close and reopen PowerShell after installation. Check that the commands are
available:

```powershell
git --version
py -3.12 --version
uv --version
```

If `py -3.12` is not recognized, rerun the Python installer and enable the
launcher, or repair the Python 3.12 installation.

## Step 2: Download the project

Choose a folder for projects, then clone the repository. For example:

```powershell
New-Item -ItemType Directory -Force "$HOME\source"
Set-Location "$HOME\source"
git clone https://github.com/CesarCastroMunoz/INFO698_Publications_Exploration.git
Set-Location ".\INFO698_Publications_Exploration"
```

The commands in the rest of this guide should be run from the repository root
(the folder containing `pyproject.toml`).

## Step 3: Create the Python environment

Install Python 3.12 through uv and synchronize the project dependencies:

```powershell
uv python install 3.12
uv sync --no-dev
```

This creates a project-local `.venv` and installs the dependencies recorded in
the lock file. You do not need to activate the virtual environment when using
`uv run`.

## Step 4: Configure credentials

Create the local environment file from the provided template:

```powershell
Copy-Item .env.example prod.env
notepad prod.env
```

Fill in at least these values:

```text
NEON_DATABASE_URL=PASTE_THE_POSTGRESQL_CONNECTION_URL_FROM_YOUR_PROVIDER
OPENAI_KEY=your_openai_api_key
```

Replace the entire `NEON_DATABASE_URL` placeholder with the connection URL
supplied by your database provider. If the username or password contains
reserved URL characters, URL-encode them before putting them in the connection
URL. Do not include surrounding quotes unless your provider specifically
requires them.

For running the publication-ingestion interface, also set:

```text
OPENALEX_API_KEY=your_openalex_api_key
USER_EMAIL=you@example.com
```

`S2_API_KEY` is optional. Leave it empty to make unauthenticated Semantic Scholar
requests.

Save and close Notepad. The application reads `prod.env` from the project root.
Environment variables already set in PowerShell take precedence over values in
that file. `prod.env` contains secrets and is ignored by Git; do not commit it,
send it to others, or paste it into support messages.

## Step 5: Create the database schema

The PostgreSQL server must have the pgvector extension available. The project
setup script enables `vector` and `pg_trgm`, creates the publication and graph
tables, and creates the required indexes. It uses `CREATE TABLE IF NOT EXISTS`
and does not drop existing tables in its current main block.

From the repository root, with `prod.env` configured:

```powershell
uv run python src\Ingest_Publications\setup_postgreDB.py
```

The database user must have permission to connect, create extensions (or have
them enabled by an administrator), create tables, and create indexes. This
project uses pgvector's `vector` type and 512-dimensional embeddings; a standard
PostgreSQL database without pgvector support is not sufficient.

After setup, verify that the `vector` extension is enabled by connecting to the
target database using its SQL console and running:

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

The query should return a version. If it returns no rows or the setup command
reports insufficient permissions, ask the database administrator or provider
to install and enable pgvector and grant the necessary setup permissions.

The setup script creates an **empty schema**; it does not download or populate
publication and graph data. The Home page, Search, and Explorer will need records
to return useful results. Use the separate ingestion interface to collect and
load data, or connect to a database that already contains it.

The setup script's current main block has the graph-table drop calls commented
out. Do not uncomment or run those `drop_table` calls against a database whose
data you want to keep. `CREATE TABLE IF NOT EXISTS` does not update an existing
table to a newer schema; it is an initial setup helper, not a general database
migration system.

## Step 6: Start the application

From the project root:

```powershell
uv run streamlit run src\stapp\app.py
```

Streamlit prints a local URL, usually `http://localhost:8501`. Open it in a
browser on the same PC. Keep the PowerShell window open while using the app.
Press **Ctrl+C** in that window to stop the server.

The main app has Home, Search, Explorer, and AI Assistant pages. AI Assistant
is currently a placeholder. Search and Explorer require both a reachable,
populated database and a valid OpenAI API key.

## Optional: Run the publication-ingestion interface

The ingestion interface retrieves publications and processes them into the
database. It is separate from the main exploration app and may incur OpenAI API
charges during embedding. OpenAlex credentials are needed to search OpenAlex;
Semantic Scholar API credentials are optional.

Install the additional local GLiNER extraction dependency:

```powershell
uv sync --extra extraction --no-dev
```

Then launch the ingestion interface:

```powershell
uv run streamlit run src\Ingest_Publications\data_pipeline_ui.py
```

The first graph-extraction run downloads the GLiNER model from Hugging Face and
requires internet access. This can take time and use substantial disk space.
The model download is not required just to run the main app.

## Optional: Run with Docker

If Docker Desktop is installed and running, build and launch the app from the
repository root:

```powershell
docker build -t info698-litexplore .
docker run --rm -p 8000:8000 --env-file prod.env info698-litexplore
```

Open `http://localhost:8000`. The same database and credential prerequisites
apply. The Docker image runs the main exploration app, not the ingestion
interface.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `uv` or `git` is not recognized | Install it, reopen PowerShell, and rerun the version check in Step 1. |
| Python 3.12 is unavailable | Run `uv python install 3.12`, then retry `uv sync --no-dev`. |
| Missing `NEON_DATABASE_URL` or connection error | Confirm `prod.env` is in the repository root, the URL is correct, and the database allows connections from this network. |
| Missing OpenAI API key or API authentication error | Check the `OPENAI_KEY` variable spelling and confirm the key is active and has API access. |
| Home shows no publications or graph example | Confirm the database has publication and knowledge-graph records in the expected tables. |
| Search returns no matches | Confirm publication embeddings exist; try a different query and check the app's terminal output. |
| GLiNER import or model-download error | Run `uv sync --extra extraction --no-dev`; check internet access and available disk space. |
| PowerShell cannot find a file | Make sure the current directory is the cloned repository root. |

For pipeline behavior and database caveats, see the
[Publication Data Pipeline](Publication%20Data%20Pipeline.md) documentation.
