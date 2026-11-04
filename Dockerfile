FROM python:3.12-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG PIP_INDEX_URL=https://pypi.org/simple
# Test tools are installed only when asked for (docker-compose.yml does this
# for local development). A production image stays without them.
ARG INSTALL_DEV=false

COPY requirements.txt requirements-dev.txt ./
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements-dev.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
