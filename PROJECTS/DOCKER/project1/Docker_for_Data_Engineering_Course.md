# Docker for Data Engineering — A Complete Course

A practical, ground-up course on Docker built specifically around the problems
data engineers actually have: reproducible environments, multi-service stacks
(databases, queues, orchestrators), and pipelines that run the same way on
your laptop, in CI, and in production. The course ends with a full, working
ETL pipeline you can run with one command.

**Companion project:** `docker-etl-example.zip` (shared alongside this
document) contains every file discussed in Module 5, fully working.

---

## Table of Contents

1. Why Docker Matters in Data Engineering
2. Docker Core Concepts
3. Writing Dockerfiles for Data Workloads
4. Docker Compose: Orchestrating Multi-Service Pipelines
5. Hands-On Project: A Containerized ETL Pipeline
6. Running, Inspecting, and Debugging the Pipeline
7. Production Best Practices
8. Where to Go Next (Airflow, Kubernetes, CI/CD)
9. Command Cheat Sheet

---

## Module 1 — Why Docker Matters in Data Engineering

Data engineering has a specific version of the "works on my machine" problem:
a pipeline that depends on pandas 2.x, a specific ODBC driver, a particular
Java version for Spark, and a locale setting that only your laptop has. Move
that pipeline to a teammate's machine, a CI runner, or a production server,
and something breaks.

Docker solves this by packaging **the code and everything it depends on**
(Python version, OS libraries, drivers, environment variables) into a single
portable unit called an **image**. That image runs identically everywhere
Docker runs.

For data engineers specifically, Docker earns its keep in four ways:

- **Reproducibility.** The exact environment a pipeline was built and tested
  in is the exact environment it runs in later — no dependency drift.
- **Isolation.** Pipeline A needs pandas 1.5; Pipeline B needs pandas 2.2.
  Each gets its own container, no conflict, no shared virtualenv juggling.
- **Disposable infrastructure for development.** Need a Postgres warehouse,
  a Kafka broker, and Redis to test locally? `docker compose up` gets you
  all three in under a minute, and `docker compose down` removes them
  completely — nothing installed on your actual machine.
- **A common unit for orchestrators.** Airflow's `DockerOperator`,
  Kubernetes `Jobs` and `CronJobs`, AWS ECS tasks — virtually every modern
  scheduler and orchestrator runs *containers*. Learning Docker is what lets
  a pipeline you write today scale onto any of those tomorrow, unchanged.

---

## Module 2 — Docker Core Concepts

A few terms come up constantly. Getting them straight now makes everything
later much easier.

| Term | What it is |
|---|---|
| **Image** | A read-only, versioned snapshot: code + runtime + libraries + config. Think of it like a class definition. |
| **Container** | A running (or stopped) *instance* of an image. You can run many containers from one image, just like many objects from one class. |
| **Dockerfile** | A text file of instructions describing how to build an image. |
| **Layer** | Each Dockerfile instruction produces a cached layer. Unchanged layers are reused on rebuild, which is why instruction *order* in a Dockerfile matters for speed. |
| **Registry** | Where images are stored and shared (Docker Hub, AWS ECR, Google Artifact Registry, GitHub Container Registry). `docker push` / `docker pull`. |
| **Volume** | A mechanism for persisting data outside a container's own filesystem, so data survives even when the container is removed. |
| **Network** | A virtual network Docker creates so containers can talk to each other by name, isolated from the host unless you explicitly expose a port. |

### The essential commands

```bash
docker build -t my-image:1.0 .     # Build an image from a Dockerfile in the current dir
docker images                      # List images on this machine
docker run my-image:1.0            # Start a container from an image
docker ps                          # List running containers
docker ps -a                       # List all containers, including stopped ones
docker logs <container>            # View a container's stdout/stderr
docker exec -it <container> bash   # Open a shell inside a running container
docker stop <container>            # Stop a running container
docker rm <container>              # Remove a stopped container
docker rmi <image>                 # Remove an image
```

### Volumes vs. bind mounts

Two ways to give a container access to data on disk — you'll use both:

- **Named volume** (`docker volume create mydata`, or declared in Compose):
  Docker manages where this lives. Ideal for **stateful services**, like a
  database's data directory, that need to persist across container
  restarts and rebuilds.
- **Bind mount** (`-v /host/path:/container/path`): maps a specific folder
  on your machine directly into the container. Ideal for **source code or
  input data during development** — edit a file on your host, see the
  change immediately inside the container, no rebuild needed.

You'll see both in the ETL project below: a named volume for Postgres's
data directory, a bind mount for the `data/` folder the ETL job reads from.

---

## Module 3 — Writing Dockerfiles for Data Workloads

Here's a minimal Dockerfile for a Python data script, annotated line by line:

```dockerfile
FROM python:3.11-slim        # Start from a small, official Python base image

WORKDIR /app                 # All following instructions run relative to /app

COPY requirements.txt .      # Copy ONLY the dependency list first...
RUN pip install --no-cache-dir -r requirements.txt   # ...and install it here

COPY . .                     # THEN copy the rest of the application code

CMD ["python", "main.py"]    # Default command when the container starts
```

### Why `requirements.txt` is copied before the rest of the code

This is the single most important Dockerfile habit for data engineers to
build. Docker caches each layer and only re-runs a layer (and everything
after it) if its inputs changed. If you copied all your code *before*
running `pip install`, then **every single code edit would invalidate the
pip-install layer**, forcing a multi-minute reinstall of pandas, numpy, etc.
on every rebuild. By copying `requirements.txt` alone first, that expensive
layer is only re-run when dependencies actually change — code edits rebuild
in seconds instead of minutes.

### Choosing a base image

- `python:3.11` — full image, includes build tools; larger (~1 GB).
- `python:3.11-slim` — Debian-based, minimal; a good default (~150 MB).
- `python:3.11-alpine` — smallest, but uses musl libc instead of glibc,
  which sometimes breaks packages with compiled C extensions (a common
  surprise with `psycopg2`, `numpy` wheels, etc.). Fine for pure-Python
  dependencies; check compatibility before choosing it for data-heavy stacks.

### Multi-stage builds (for compiled dependencies)

When a package needs to be compiled from source, you often need build tools
that bloat the final image. A multi-stage build compiles in one stage and
copies only the finished artifact into a clean final stage:

```dockerfile
# Stage 1: build
FROM python:3.11 AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: final, slim runtime image
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "main.py"]
```

The final image contains only the installed packages and your code — no
compilers, no build cache, meaningfully smaller and with a smaller attack
surface.

### `.dockerignore`

Just like `.gitignore`, this keeps unnecessary files out of the **build
context** (everything Docker reads when you run `docker build`). Without
it, a stray `venv/` folder or large data dump can make every build slow and
can accidentally bake secrets or large files into your image:

```
__pycache__/
*.pyc
.git
.env
.venv
venv/
*.egg-info
```

---

## Module 4 — Docker Compose: Orchestrating Multi-Service Pipelines

Real pipelines are rarely one container. A typical local data stack might
need a source database, a target warehouse, maybe a queue, and the pipeline
code itself — four or five containers that all need to start in the right
order and talk to each other. **Docker Compose** describes that whole stack
declaratively in one YAML file.

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: etl_user
      POSTGRES_PASSWORD: etl_pass
      POSTGRES_DB: warehouse
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data

  etl:
    build: .
    depends_on:
      - postgres
    environment:
      DB_HOST: postgres

volumes:
  pg_data:
```

Key things to notice:

- **`image` vs `build`.** `postgres` uses a pre-built public image pulled
  straight from Docker Hub. `etl` uses `build: .`, telling Compose to build
  an image from the local `Dockerfile` instead.
- **Service name = hostname.** Inside this Compose network, the `etl`
  container can reach Postgres at the hostname `postgres` — that's just the
  service name, resolved automatically by Docker's internal DNS. No IP
  addresses, no `localhost`.
- **`depends_on`.** Controls *start order*. On its own it only waits for the
  container process to start, not for Postgres to actually be ready to
  accept connections — which is a very common source of "connection
  refused" errors on the first run. The fix is a **healthcheck**, shown in
  Module 5.
- **`ports` vs no `ports`.** `postgres` publishes port 5432 to your host
  machine (so tools like `psql` on your laptop can connect); `etl` doesn't
  need to publish anything since nothing outside the Docker network needs
  to reach it directly.
- **Top-level `volumes:`.** Declares the named volume so Postgres's data
  directory survives `docker compose down` (though not `docker compose down
  -v`, which deliberately deletes it).

Run the whole stack with:

```bash
docker compose up --build     # build images if needed, start everything
docker compose down           # stop and remove containers (volumes kept)
docker compose down -v        # also delete named volumes (full reset)
```

---

## Module 5 — Hands-On Project: A Containerized ETL Pipeline

Time to put it together. This is a real, working pipeline — the same code
is provided as a ready-to-run zip alongside this document.

### The scenario

A retailer drops a daily CSV of raw sales transactions. We need to:

1. **Extract** the raw CSV.
2. **Transform** it: clean bad rows, compute revenue, aggregate into daily
   revenue per product category.
3. **Load** the result into a PostgreSQL warehouse table for analysts to
   query.

Everything — the warehouse database *and* the pipeline code — runs in
Docker. `docker compose up` is the only setup step required, on any machine
with Docker installed.

### Project structure

```
docker-etl-example/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .dockerignore
├── README.md
├── data/
│   └── raw_sales.csv
└── etl/
    ├── __init__.py
    ├── extract.py
    ├── transform.py
    ├── load.py
    └── main.py
```

Separating `extract` / `transform` / `load` into their own modules isn't
just tidiness — it means each stage can be tested, reasoned about, and
replaced independently. Swapping the CSV source for an API later only
touches `extract.py`.

### `data/raw_sales.csv` (sample source data)

A small sample with two intentionally dirty rows — a missing quantity and a
negative quantity — to make the cleaning logic in `transform.py` visible:

```csv
order_date,product_category,quantity,unit_price
2026-01-01,Electronics,2,199.99
2026-01-01,Clothing,5,25.50
2026-01-02,Electronics,,299.99
2026-01-03,Clothing,-1,25.50
...
```

### `etl/extract.py`

```python
import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)
RAW_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "raw_sales.csv"


def extract() -> pd.DataFrame:
    """Read raw sales records from the source CSV and return a DataFrame."""
    logger.info("Extracting data from %s", RAW_DATA_PATH)
    df = pd.read_csv(RAW_DATA_PATH)
    logger.info("Extracted %d rows", len(df))
    return df
```

Nothing fancy — but notice the path is built relative to the file itself
(`Path(__file__)...`), not a hardcoded absolute path. That's what makes it
work identically on your laptop and inside the container, where the code
lives at `/app`.

### `etl/transform.py`

```python
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def transform(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Clean raw sales data and aggregate daily revenue per category."""
    df = raw_df.copy()
    logger.info("Starting transform on %d rows", len(df))

    # --- Clean ---
    df = df.dropna(subset=["order_date", "product_category", "quantity", "unit_price"])
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.date
    df["quantity"] = df["quantity"].astype(int)
    df["unit_price"] = df["unit_price"].astype(float)

    before = len(df)
    df = df[(df["quantity"] > 0) & (df["unit_price"] > 0)]
    logger.info("Dropped %d invalid rows during cleaning", before - len(df))

    # --- Enrich ---
    df["total_amount"] = df["quantity"] * df["unit_price"]

    # --- Aggregate ---
    daily_category_revenue = (
        df.groupby(["order_date", "product_category"], as_index=False)
        .agg(
            total_revenue=("total_amount", "sum"),
            orders=("total_amount", "count"),
            units_sold=("quantity", "sum"),
        )
        .sort_values(["order_date", "product_category"])
        .reset_index(drop=True)
    )
    logger.info("Transform complete: %d aggregated rows", len(daily_category_revenue))
    return daily_category_revenue
```

This is where the actual business logic sits: what counts as a "bad" row,
how revenue is calculated, and what granularity the warehouse table should
have. Everything above it (extract) and below it (load) is comparatively
generic plumbing.

### `etl/load.py`

```python
import logging
import os
import pandas as pd
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)
TABLE_NAME = "daily_category_revenue"


def _get_engine():
    user = os.environ.get("DB_USER", "etl_user")
    password = os.environ.get("DB_PASSWORD", "etl_pass")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "warehouse")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    return create_engine(url)


def load(df: pd.DataFrame) -> None:
    """Load the aggregated DataFrame into Postgres, replacing prior data."""
    engine = _get_engine()
    logger.info("Loading %d rows into table '%s'", len(df), TABLE_NAME)
    df.to_sql(TABLE_NAME, con=engine, if_exists="replace", index=False)
    logger.info("Load complete")
```

Notice **none of the connection details are hardcoded** — they all come
from environment variables with sensible local defaults. This is what lets
`docker-compose.yml` point this exact code at the `postgres` service by
just setting `DB_HOST=postgres`, with zero code changes. The same image
could point at a production RDS instance by changing only environment
variables at deploy time.

### `etl/main.py`

```python
import logging
from etl.extract import extract
from etl.transform import transform
from etl.load import load

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    logger.info("=== ETL pipeline starting ===")
    raw_df = extract()
    clean_df = transform(raw_df)
    load(clean_df)
    logger.info("=== ETL pipeline finished successfully ===")


if __name__ == "__main__":
    run_pipeline()
```

The orchestration layer: three function calls, in order, with logging
around them. Real pipelines add try/except error handling and alerting
here — see Module 7.

### `requirements.txt`

```
pandas==2.2.2
SQLAlchemy==2.0.30
psycopg2-binary==2.9.9
```

Pinned exact versions — not `pandas` or `pandas>=2.0` — so a rebuild six
months from now installs the *same* versions, not whatever is newest at
that moment. This is one of Docker's reproducibility promises, and pinning
loosely quietly throws it away.

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY etl/ ./etl/
COPY data/ ./data/

RUN useradd --create-home appuser
USER appuser

CMD ["python", "-m", "etl.main"]
```

Same dependency-caching pattern from Module 3, plus a non-root `appuser` —
containers run as root by default, which is more privilege than a batch
script needs.

### `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16
    container_name: dw_postgres
    environment:
      POSTGRES_USER: etl_user
      POSTGRES_PASSWORD: etl_pass
      POSTGRES_DB: warehouse
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U etl_user -d warehouse"]
      interval: 5s
      timeout: 5s
      retries: 5

  etl:
    build: .
    container_name: sales_etl
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: warehouse
      DB_USER: etl_user
      DB_PASSWORD: etl_pass
    volumes:
      - ./data:/app/data

  adminer:
    image: adminer
    container_name: dw_adminer
    ports:
      - "8080:8080"
    depends_on:
      - postgres

volumes:
  pg_data:
```

This is the piece that ties the whole module together:

- The **healthcheck** on `postgres` runs `pg_isready` every 5 seconds. The
  `etl` service's `depends_on: postgres: condition: service_healthy` means
  Docker won't even start the `etl` container until that healthcheck
  passes — solving the "started but not actually ready" race condition
  from Module 4.
- `./data:/app/data` is a **bind mount**: it maps the local `data/` folder
  into the container, so replacing `raw_sales.csv` on your machine and
  re-running the pipeline picks up the new file with no rebuild.
- `pg_data` is a **named volume**: Postgres's actual database files live
  there, persisting across restarts.
- `adminer` is an optional, tiny web UI for browsing the warehouse without
  needing `psql` installed — genuinely useful when you just want to eyeball
  a table.

---

## Module 6 — Running, Inspecting, and Debugging the Pipeline

With Docker installed and the project folder in hand:

```bash
# Build the ETL image and start everything
docker compose up --build
```

You'll see Postgres start, become healthy, then the `etl` container run and
exit — that's expected, since this is a one-shot batch job rather than a
long-running server.

**Check the result:**

```bash
docker exec -it dw_postgres psql -U etl_user -d warehouse \
  -c "SELECT * FROM daily_category_revenue ORDER BY order_date, product_category;"
```

Or open `http://localhost:8080` (Adminer) and log in with server
`postgres`, username `etl_user`, password `etl_pass`, database `warehouse`.

**Re-run after a code change:**

```bash
docker compose up --build etl
```

**View logs from a specific service:**

```bash
docker compose logs -f etl
```

**Get a shell inside the ETL container to poke around:**

```bash
docker compose run etl bash
# then, inside the container:
python -m etl.extract   # test just one stage in isolation
```

**Full reset (including deleting warehouse data):**

```bash
docker compose down -v
```

---

## Module 7 — Production Best Practices

A few habits that separate a demo pipeline from one you'd trust in
production:

- **Pin every version** — base image tag, package versions in
  `requirements.txt`. `python:3.11-slim` today isn't the same bytes as
  `python:3.11-slim` in six months; consider pinning to a digest
  (`python:3.11-slim@sha256:...`) for maximum reproducibility in critical
  pipelines.
- **Never hardcode credentials.** Environment variables (as this project
  does), Docker secrets, or a secrets manager (AWS Secrets Manager, HashiCorp
  Vault) — not values baked into a Dockerfile or committed `.env` file.
- **Make loads idempotent.** This example uses `if_exists="replace"` for
  simplicity, which is fine for a small demo table but re-creates the whole
  table on every run. Production pipelines more often use an upsert (`INSERT
  ... ON CONFLICT`) or a partition-swap / truncate-and-load pattern scoped
  to just the affected date range, so re-running a failed job doesn't
  duplicate or destroy unrelated data.
- **Log to stdout/stderr, not to a file inside the container.** Container
  filesystems are ephemeral by default; orchestrators (Compose, Kubernetes,
  ECS) already collect stdout/stderr centrally. This project's
  `logging.basicConfig` does this correctly out of the box.
- **Add real error handling.** `main.py` here is intentionally minimal for
  clarity — production code wraps each stage in try/except, sends alerts on
  failure (Slack, PagerDuty, email), and considers whether partial failures
  should stop the whole pipeline or continue.
- **Keep images small.** Smaller images pull faster, deploy faster, and have
  a smaller attack surface. Use `-slim` base images, multi-stage builds for
  anything compiled, and a thorough `.dockerignore`.
- **Set resource limits in production.** Compose and Kubernetes both support
  memory/CPU limits per container — important so one runaway pandas job
  can't starve everything else on a shared host.
- **Health-check every service your pipeline depends on**, not just
  Postgres — the same pattern applies to Kafka, Redis, or any other
  dependency your `depends_on` chain relies on.

---

## Module 8 — Where to Go Next

This project runs one pipeline once, on demand. Real data platforms usually
need scheduling, retries, dependency graphs between tasks, and
observability. A few natural next steps, roughly in order of how most teams
progress:

- **Airflow + Docker.** Airflow itself is commonly run via Docker Compose
  (webserver, scheduler, and a metadata Postgres, all as services), and its
  `DockerOperator` can run each pipeline *task* as its own container — so
  the `etl` service built here could become a single task in a larger DAG
  with retries, scheduling, and a UI.
- **CI/CD for pipeline images.** On every commit, a CI pipeline (GitHub
  Actions, GitLab CI, etc.) builds the image, runs tests inside a container,
  and pushes it to a registry (Docker Hub, ECR) — so what's deployed is
  exactly what was tested.
- **Kubernetes for scale.** `CronJob` resources run containerized batch
  jobs on a schedule; `Jobs` run one-off tasks — the natural next step once
  a single Docker host isn't enough.
- **Bigger transforms.** For data volumes pandas can't comfortably handle in
  memory, the same containerization patterns apply to Spark or dbt —
  the Docker concepts here (layer caching, Compose networking, volumes,
  health checks) carry over directly.

---

## Command Cheat Sheet

```bash
# Images
docker build -t name:tag .          # Build an image
docker images                       # List images
docker rmi <image>                  # Remove an image

# Containers
docker run <image>                  # Run a container
docker ps / docker ps -a            # List running / all containers
docker exec -it <container> bash    # Shell into a running container
docker logs -f <container>          # Follow a container's logs
docker stop <container>             # Stop a container
docker rm <container>               # Remove a stopped container

# Compose
docker compose up --build           # Build + start the whole stack
docker compose up --build <service> # Build + start just one service
docker compose down                 # Stop and remove containers
docker compose down -v              # Also remove named volumes
docker compose logs -f <service>    # Follow logs for one service
docker compose run <service> bash   # One-off shell inside a service

# Cleanup
docker system prune                 # Remove unused containers/images/networks
docker volume prune                 # Remove unused volumes
```
