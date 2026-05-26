FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 (pykrx 등이 lxml/네트워크를 씀)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt* /app/
# setuptools 81+에서 pkg_resources 제거됨 → pykrx가 import 실패함
# requirements.txt 핀과 별개로 base에 강제 설치 (이중 안전장치)
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir "setuptools>=70,<81" wheel && \
    if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi && \
    python -c "import pkg_resources, setuptools; print('pkg_resources OK, setuptools', setuptools.__version__)" && \
    python -c "from pykrx import stock"

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
