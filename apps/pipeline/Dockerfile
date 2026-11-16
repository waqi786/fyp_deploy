FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY resora_pipeline ./resora_pipeline
RUN pip install --no-cache-dir ".[spark,s3,kafka,faiss,postgres]"
RUN useradd --create-home pipeline && mkdir -p /data/output && chown pipeline /data/output
USER pipeline
ENTRYPOINT ["python", "-m", "resora_pipeline"]
CMD ["status"]
