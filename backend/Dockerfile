FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps needed by matplotlib + asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libfreetype6 \
    libjpeg62-turbo \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -e .

# Copy app code + alembic (migrations run as a separate Container App Job)
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Non-root user
RUN useradd --uid 10001 --no-create-home --shell /sbin/nologin appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
