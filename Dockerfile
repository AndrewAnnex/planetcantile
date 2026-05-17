# syntax=docker/dockerfile:1

# Stage 1: install dependencies
FROM python:3.12-slim AS builder

WORKDIR /build
# Create a virtual environment so the entire installation can be copied as a unit to stage 2.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./

RUN pip install --no-cache-dir --upgrade pip

# Minimal src layout allows setuptools to resolve package metadata without the full source tree.
# pip download requires only metadata to resolve the dependency graph; replaced by the full COPY src/ below.
RUN mkdir -p src/planetcantile && touch src/planetcantile/__init__.py

# Download all wheels to a local cache; network is available at this stage but no install hooks execute.
# --prefer-binary avoids source builds; rasterio/pyproj binary wheels bundle GDAL/PROJ.
RUN pip download --no-cache-dir --prefer-binary --dest /wheels setuptools wheel ".[app]"

# Install from the local wheel cache with network access disabled.
RUN --network=none pip install --no-cache-dir --no-index --find-links /wheels ".[app]"

COPY src/ ./src/
# Network-isolated install prevents the package from fetching additional dependencies at install time.
RUN --network=none pip install --no-cache-dir --no-index --find-links /wheels --no-deps .

# Stage 2: production
FROM python:3.12-slim AS server

# rasterio's manylinux wheel bundles GDAL/PROJ but requires system libexpat at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

# Run as a non-root user with no home directory and no login shell for security hardening.
RUN useradd --no-create-home --shell /bin/false --uid 1001 appuser

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER appuser

ENV WORKERS=1

EXPOSE 8000
CMD ["sh", "-c", "uvicorn planetcantile.app:app --host 0.0.0.0 --port 8000 --workers ${WORKERS}"]
