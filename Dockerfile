# Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

# Copy dependency manifest first for layer caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/

# Switch to the non-root user provided by the Playwright image
USER pwuser

CMD ["python", "-m", "src.main"]
