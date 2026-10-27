# Match the project's Python runtime using a smaller Debian-based image.
FROM python:3.12.10-slim

# Copy uv from its official image for dependency installation.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Cache dependency installation separately from application code changes.
# This command resolves pyproject.toml dependencies; it does not use uv.lock.
COPY pyproject.toml uv.lock* ./
RUN uv pip install --system -r pyproject.toml

# Copy application code only; supply secrets through runtime environment variables.
COPY src/ /app/src/

# Document the container port; publish it with docker run -p 8000:8000.
EXPOSE 8000

# Listen on all container interfaces so the published port is reachable.
CMD ["python", "-m", "streamlit", "run", "src/stapp/app.py", "--server.port", "8000", "--server.address", "0.0.0.0"]