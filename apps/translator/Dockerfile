FROM python:3.11-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 HF_HOME=/models/huggingface TRANSFORMERS_CACHE=/models/huggingface
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "transformers>=4.45,<5" "sentencepiece>=0.2,<1" "torch>=2.5,<3"
COPY main.py ./main.py
EXPOSE 8090
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
