FROM python:3.11-slim

ARG INSTALL_CJK_FONTS=1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PYTHONHASHSEED=0 \
    TORCH_HOME=/cache/torch

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && if [ "$INSTALL_CJK_FONTS" = "1" ]; then \
         apt-get install -y --no-install-recommends fonts-noto-cjk; \
       fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY env/requirements-base.txt /tmp/requirements-base.txt
RUN pip install -r /tmp/requirements-base.txt

COPY env/requirements-dl.txt /tmp/requirements-dl.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements-dl.txt

COPY env/requirements-web.txt /tmp/requirements-web.txt
RUN pip install -r /tmp/requirements-web.txt

COPY . /app

# 命令行入口在阶段一实现后启用：
# ENTRYPOINT ["python", "-m", "docnorm.cli"]
CMD ["python", "scripts/env_smoke.py"]
