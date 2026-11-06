FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_DATA_HOME=/models \
    RESORA_MODELS_DIR=/models \
    LOCAL_TRANSLATION_THREADS=1 \
    LOCAL_TRANSLATION_MAX_LOADED_MODELS=1
WORKDIR /srv
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py engine_manager.py ./
COPY translator_local ./translator_local
EXPOSE 8091
CMD ["python", "-m", "translator_local"]
