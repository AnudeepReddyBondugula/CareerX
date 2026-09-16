# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# CareerX
#
# The image is built around Tectonic rather than a TeX Live installation.
# Tectonic is a single ~35 MB binary that downloads only the LaTeX packages a
# document actually uses and caches them, so an image that can typeset a
# resume with fontawesome5 costs a few hundred megabytes instead of several
# gigabytes. The bundle is warmed at build time by compiling both templates,
# which also fails the build if a template is broken.
# ---------------------------------------------------------------------------

ARG PYTHON_VERSION=3.13
ARG TECTONIC_VERSION=0.15.0

# ---------------------------------------------------------------------------
# Stage 1: Python dependencies
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies are installed from the lockfile before the source is copied, so
# an application-only change does not invalidate the dependency layer.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG TECTONIC_VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    ARTIFACT_DIR=/var/lib/careerx/artifacts \
    TECTONIC_CACHE_DIR=/var/cache/tectonic \
    HOST=0.0.0.0 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Tectonic ships a static musl binary, so it runs as-is on a slim Debian base.
RUN set -eux; \
    curl -fsSL \
      "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/tectonic.tar.gz; \
    tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin tectonic; \
    rm /tmp/tectonic.tar.gz; \
    tectonic --version

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY scripts ./scripts
COPY pyproject.toml README.md ./

# Warm Tectonic's package cache and prove every template typesets. Without
# this the first request on a cold container pays for a package download; with
# it, a template that does not compile fails the build instead of a request.
RUN mkdir -p "${TECTONIC_CACHE_DIR}" && python scripts/warm_templates.py

# Run unprivileged. The artifact directory is the only writable path needed.
RUN useradd --system --create-home --uid 10001 careerx \
    && mkdir -p "${ARTIFACT_DIR}" \
    && chown -R careerx:careerx "${ARTIFACT_DIR}" "${TECTONIC_CACHE_DIR}"

USER careerx

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "/app/scripts/healthcheck.py"]

# `sh -c` so $PORT, which hosting platforms inject at runtime, is honoured.
CMD ["sh", "-c", "exec uvicorn careerx.api.app:app --host \"${HOST}\" --port \"${PORT}\""]
