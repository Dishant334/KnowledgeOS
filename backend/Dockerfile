# Dockerfile

#1. Base docker image
FROM python:3.11-slim AS base

#2. Install some deps
# tesseract needed for OCR, libpq for psycopg, build tools for any
# packages that compile from source (some ML deps do)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

#3. Work dir in
WORKDIR /app

#4.Copy req.txt 
COPY requirements.txt .

#5. Install everything from requirement.txt
RUN pip install --no-cache-dir -r requirements.txt

#6. Copy everything
COPY . .

#Cache all fastembed stuff
# fastembed downloads BGE-M3 + BM25 model weights on first use and
# caches them under this path — mounted as a named volume in compose
# so the models aren't re-downloaded every container restart.
ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache

#expose port
EXPOSE 8000

#run app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]