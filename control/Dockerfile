FROM python:3.12-slim-trixie

# NOTE (patched 2026-07-22): PyGObject 3.56.x (pulled in by requirements.txt's
# PyGObject>=3.48,<4.0) links against girepository-2.0, which only exists on
# Debian trixie — bookworm (the default `python:3.12-slim` tag) only ships
# girepository1.0-dev / libgirepository1.0-dev and will fail at pip-install
# time with a meson "Dependency 'girepository-2.0' is required but not
# found" error. Pinning the base image to -trixie and swapping the dev
# package fixes this. `python3-gi` (the Debian-packaged PyGObject binding) is
# intentionally NOT installed via apt: it would conflict with/shadow the
# pip-installed PyGObject==3.56.3 pinned in requirements.txt, which is the
# version this Dockerfile is actually built and tested against.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config \
    libpango1.0-dev libcairo2-dev libgirepository-2.0-dev \
    gir1.2-pango-1.0 \
    libzbar0 libpq-dev \
    libgl1 \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/app
CMD ["python", "-m", "imagin.cli"]
