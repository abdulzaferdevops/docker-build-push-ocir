# Lab 4: multi-stage image for the Inventory API (Flask + gunicorn).
#
#   test     lint + unit tests; the pipeline builds this target first, so a failing
#            test stops the build before any image is produced
#   build    installs runtime dependencies into a virtualenv
#   runtime  slim final image: no compilers, no test tools, non-root user
#
# Build args are written into a RELEASE file so /health reports the exact build.

ARG PYTHON_IMAGE=python:3.11-slim

# ---------- test ----------
FROM ${PYTHON_IMAGE} AS test
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /src
COPY app/requirements.txt app/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY app/ ./
RUN flake8 && pytest -p no:cacheprovider -q

# ---------- build ----------
FROM ${PYTHON_IMAGE} AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY app/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt && /opt/venv/bin/python -m pip uninstall -y pip setuptools wheel

# ---------- runtime ----------
FROM ${PYTHON_IMAGE} AS runtime

ARG RELEASE=dev
ARG COMMIT=unknown
ARG BUILT=unknown
ARG SOURCE=https://github.com/abdulzaferdevops/docker-build-push-ocir

LABEL org.opencontainers.image.title="inventory-api" \
      org.opencontainers.image.description="Lab 4: Flask inventory API built and pushed to OCIR by Jenkins" \
      org.opencontainers.image.source="${SOURCE}" \
      org.opencontainers.image.revision="${COMMIT}" \
      org.opencontainers.image.version="${RELEASE}" \
      org.opencontainers.image.created="${BUILT}" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Unprivileged user with a fixed UID (predictable for Podman/OKE security contexts)
RUN python -m pip uninstall -y pip setuptools wheel && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY app/app.py ./
COPY app/data ./data
RUN printf 'release=%s\ncommit=%s\nbuilt=%s\n' "${RELEASE}" "${COMMIT}" "${BUILT}" > RELEASE \
 && chown -R root:root /app && chmod -R a+rX,go-w /app

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["sh", "-c", "exec gunicorn --workers 2 --bind 0.0.0.0:${PORT} --access-logfile - app:app"]
