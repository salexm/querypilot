FROM python:3.12-slim

WORKDIR /app

# Production installs runtime packages only. Compose passes the dev file for tests.
ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r ${REQUIREMENTS}

COPY . .

RUN useradd --create-home app
USER app

# Hosting platforms choose the port through PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
