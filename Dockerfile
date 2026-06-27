FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PDF parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY rfp_extractor/ rfp_extractor/

# Install package with all extras
RUN pip install --no-cache-dir -e ".[openai,anthropic,gemini]"

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "-c", "from rfp_extractor.api import start; start()"]