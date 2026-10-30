# Build, runtime and test stages (ADR-005). The runtime image is the last
# stage, so a plain `docker build` produces it.

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM python:3.14-slim@sha256:82abc9f53600280b0757126f83c5a7d47088592d2acb6b4c0b9e97f76865508c AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first: this layer changes only with the lock.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.14-slim@sha256:82abc9f53600280b0757126f83c5a7d47088592d2acb6b4c0b9e97f76865508c AS runtime
LABEL org.opencontainers.image.title="enterich" \
      org.opencontainers.image.licenses="Apache-2.0"
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["enterich"]

# The runtime stage plus dev dependencies and tests, all from the lock.
FROM runtime AS test
USER root
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
# The test group added to the runtime's environment, leaving Enterich as installed.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --group test --no-install-project --inexact
# tests/repo and tests/readme.py read repository files; they run on the runner only.
COPY tests ./tests
USER 10001:10001
ENTRYPOINT []
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/unit", "tests/e2e"]

FROM runtime
