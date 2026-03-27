FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY pyproject.toml ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
RUN pip install --no-cache-dir -e ".[prod]"

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
