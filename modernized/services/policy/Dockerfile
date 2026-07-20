# Policy Service — independently deployable container (ADR-001).
# Build context must be the repository root:
#   docker build -f modernized/services/policy/Dockerfile -t nn-policy .
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY modernized/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared governance package and the modernized services.
COPY governance/ ./governance/
COPY modernized/ ./modernized/

# Run as a non-root user (least privilege).
RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8002

EXPOSE 8002

CMD ["sh", "-c", "uvicorn modernized.services.policy.api:app --host 0.0.0.0 --port ${PORT}"]
