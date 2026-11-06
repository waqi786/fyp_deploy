from __future__ import annotations

import os
from functools import lru_cache
from threading import Lock

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

MODEL_ID = os.getenv("MADLAD_MODEL_ID", "google/madlad400-3b-mt")
DEVICE = "cuda" if torch.cuda.is_available() and os.getenv("MADLAD_DEVICE", "auto") != "cpu" else "cpu"
MODEL_LOCK = Lock()
app = FastAPI(title="Resora MADLAD Translation", docs_url=None, redoc_url=None)


class TranslationRequest(BaseModel):
    segments: list[str] = Field(min_length=1, max_length=24)
    source_language: str = "auto"
    target_language: str


class TranslationResponse(BaseModel):
    translations: list[str]
    model: str
    device: str


@lru_cache(maxsize=1)
def load_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID, torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32)
    model.to(DEVICE)
    model.eval()
    return tokenizer, model


def language_tag(code: str) -> str:
    canonical = code.strip().replace("_", "-")
    mapping = {"zh-Hans": "zh", "zh-Hant": "yue", "pt-BR": "pt", "pt-PT": "pt", "pa-Arab": "pa"}
    return mapping.get(canonical, canonical.split("-")[0])


@app.get("/health")
def health():
    return {"status": "ready" if load_model() else "loading", "model": MODEL_ID, "device": DEVICE}


@app.post("/translate", response_model=TranslationResponse)
def translate(payload: TranslationRequest):
    if any(len(segment) > 10000 for segment in payload.segments):
        raise HTTPException(status_code=413, detail="A translation segment is too long")
    target = language_tag(payload.target_language)
    inputs = [f"<2{target}> {segment}" for segment in payload.segments]
    try:
        tokenizer, model = load_model()
        with MODEL_LOCK, torch.inference_mode():
            encoded = tokenizer(inputs, return_tensors="pt", padding=True, truncation=True, max_length=2048).to(DEVICE)
            generated = model.generate(**encoded, max_new_tokens=1024, num_beams=1)
            outputs = tokenizer.batch_decode(generated, skip_special_tokens=True)
        if len(outputs) != len(payload.segments) or any(not output.strip() for output in outputs):
            raise RuntimeError("MADLAD returned an incomplete batch")
        return TranslationResponse(translations=outputs, model=MODEL_ID, device=DEVICE)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Translation service is temporarily unavailable") from exc
