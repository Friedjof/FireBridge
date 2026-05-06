FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        android-tools-adb \
        android-tools-fastboot \
        ca-certificates \
        usbutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY main.py ./
COPY firebridge ./firebridge
COPY tools ./tools
COPY config ./config

RUN pip install .

VOLUME ["/root/.android"]

ENTRYPOINT ["firebridge"]
CMD ["serve"]
