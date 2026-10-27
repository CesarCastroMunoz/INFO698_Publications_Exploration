# Use a lightweight Python base image
FROM python:3.12.10-slim

# Install uv directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Copy the dependency files first (to cache this layer)
COPY pyproject.toml uv.lock* ./

# Install dependencies globally in the container using uv
RUN uv pip install --system .

# Copy your source code into the container
COPY src/ /app/src/

# Expose Streamlit's port
EXPOSE 8000

# Start the Streamlit application
CMD ["python", "-m", "streamlit", "run", "src/stapp/app.py", "--server.port", "8000", "--server.address", "0.0.0.0"]