FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app app
COPY tests tests
RUN useradd --uid 10001 --create-home studio && mkdir -p /data/media /data/models && chown -R studio:studio /data
USER studio
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-access-log"]
