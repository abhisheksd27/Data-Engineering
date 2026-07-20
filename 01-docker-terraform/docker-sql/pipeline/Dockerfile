FROM python:3.13.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /code
ENV PATH="/code/.venv/bin:$PATH"

COPY pyproject.toml .python-version ./
RUN uv sync

COPY ingest_data.py .

ENTRYPOINT ["uv", "run", "python", "ingest_data.py"]