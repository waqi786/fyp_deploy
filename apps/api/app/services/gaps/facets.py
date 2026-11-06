"""Facet extraction for gap analysis: methods, datasets, tasks, domains, populations, languages and metrics.

Deterministic and explainable: every facet found in a paper keeps the sentence it came from, so each count shown to the
user can be traced back to the papers (and words) behind it. Aliases are normalised ("large language models" → "LLM").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

KINDS = ("method", "dataset", "task", "domain", "population", "language", "metric")

# label: aliases (lower-case, matched on word boundaries; the label itself is always an alias)
METHODS: dict[str, list[str]] = {
    "LLM": ["large language model", "large language models", "llms", "llm"],
    "Transformer": ["transformer", "transformers", "self-attention"],
    "BERT": ["bert", "roberta", "deberta"],
    "GPT": ["gpt", "gpt-3", "gpt-4", "chatgpt"],
    "RAG": ["retrieval-augmented generation", "retrieval augmented generation", "rag"],
    "CNN": ["convolutional neural network", "convolutional neural networks", "cnn", "cnns", "resnet"],
    "RNN / LSTM": ["recurrent neural network", "rnn", "lstm", "gru"],
    "Graph neural network": ["graph neural network", "graph neural networks", "gnn", "gnns", "graph convolutional"],
    "Diffusion model": ["diffusion model", "diffusion models", "denoising diffusion"],
    "GAN": ["generative adversarial network", "generative adversarial networks", "gan", "gans"],
    "Autoencoder": ["autoencoder", "autoencoders", "variational autoencoder", "vae"],
    "Contrastive learning": ["contrastive learning", "contrastive pre-training", "contrastive decoding"],
    "Reinforcement learning": ["reinforcement learning", "rlhf", "policy gradient", "q-learning"],
    "Transfer learning": ["transfer learning", "fine-tuning", "fine tuning", "finetuning"],
    "Federated learning": ["federated learning"],
    "Knowledge distillation": ["knowledge distillation", "distillation"],
    "Random forest": ["random forest", "random forests"],
    "Gradient boosting": ["gradient boosting", "xgboost", "lightgbm", "catboost"],
    "SVM": ["support vector machine", "support vector machines", "svm"],
    "Logistic regression": ["logistic regression"],
    "Bayesian methods": ["bayesian", "bayes"],
    "BM25": ["bm25"],
    "Vision-language model": ["vision-language model", "vision-language models", "vision language model", "vlm", "vlms", "multimodal large language model"],
    "Prompting": ["prompting", "prompt engineering", "chain-of-thought", "in-context learning", "few-shot prompting"],
    "Randomized controlled trial": ["randomized controlled trial", "randomised controlled trial", "rct"],
    "Meta-analysis": ["meta-analysis", "meta analysis", "systematic review"],
    "Survey study": ["questionnaire", "survey study", "cross-sectional survey"],
    "Qualitative interviews": ["semi-structured interviews", "qualitative interviews", "focus groups", "thematic analysis"],
    "Simulation": ["monte carlo", "agent-based model", "simulation study"],
}

TASKS: dict[str, list[str]] = {
    "Classification": ["classification", "classifier"],
    "Object detection": ["object detection"],
    "Segmentation": ["segmentation"],
    "Machine translation": ["machine translation", "translation"],
    "Summarization": ["summarization", "summarisation"],
    "Question answering": ["question answering", "qa"],
    "Information retrieval": ["information retrieval", "retrieval", "search engine"],
    "Recommendation": ["recommendation", "recommender"],
    "Forecasting": ["forecasting", "time series prediction", "time-series"],
    "Sentiment analysis": ["sentiment analysis", "sentiment"],
    "Named entity recognition": ["named entity recognition", "ner"],
    "Image captioning": ["image captioning", "captioning", "caption"],
    "Speech recognition": ["speech recognition", "asr"],
    "Anomaly detection": ["anomaly detection", "fraud detection", "intrusion detection"],
    "Hallucination": ["hallucination", "hallucinations", "factuality"],
}

DOMAINS: dict[str, list[str]] = {
    "Healthcare": ["clinical", "healthcare", "health care", "medical", "patients", "hospital"],
    "Radiology": ["radiology", "x-ray", "ct scan", "mri", "chest x-ray"],
    "Education": ["education", "students", "classroom", "learning outcomes"],
    "Finance": ["finance", "financial", "stock market", "banking"],
    "Agriculture": ["agriculture", "crop yield", "crops", "farming"],
    "Climate": ["climate", "weather", "carbon emissions"],
    "Law": ["legal", "court", "jurisprudence"],
    "Social media": ["social media", "twitter", "facebook", "tweets"],
    "Robotics": ["robot", "robotics", "robotic"],
    "Autonomous driving": ["autonomous driving", "self-driving", "autonomous vehicles"],
    "Cybersecurity": ["cybersecurity", "malware", "intrusion"],
    "Energy": ["energy", "power grid", "smart grid"],
    "E-commerce": ["e-commerce", "online retail"],
    "Mobile devices": ["mobile", "smartphone", "edge devices", "on-device"],
}

POPULATIONS: dict[str, list[str]] = {
    "Children": ["children", "child", "pediatric", "paediatric"],
    "Adolescents": ["adolescents", "teenagers", "youth"],
    "Older adults": ["older adults", "elderly", "aged care"],
    "Women": ["women", "female participants", "maternal"],
    "Rural communities": ["rural"],
    "Low-income settings": ["low-income", "low income", "developing countries", "global south", "lmics"],
    "People with disabilities": ["disabilities", "disability", "visually impaired", "blind users"],
}

LANGUAGES: dict[str, list[str]] = {
    "Low-resource languages": ["low-resource language", "low-resource languages", "under-resourced languages"],
    "Multilingual": ["multilingual", "cross-lingual", "crosslingual"],
    "English": ["english"], "Urdu": ["urdu"], "Arabic": ["arabic"], "Hindi": ["hindi"], "Bengali": ["bengali", "bangla"], "Swahili": ["swahili"],
    "Chinese": ["chinese", "mandarin"], "Spanish": ["spanish"], "French": ["french"], "Persian": ["persian", "farsi"],
}

METRICS: dict[str, list[str]] = {
    "Accuracy": ["accuracy"], "F1": ["f1", "f1-score", "f-score"], "Precision / recall": ["precision", "recall"],
    "AUC": ["auc", "auroc", "roc"], "BLEU": ["bleu"], "ROUGE": ["rouge"], "mAP": ["map", "mean average precision"],
    "RMSE / MAE": ["rmse", "mae", "mean squared error"], "Perplexity": ["perplexity"], "Latency": ["latency", "inference time"],
}

KNOWN_DATASETS = [
    "ImageNet", "COCO", "MSCOCO", "CIFAR-10", "CIFAR-100", "MNIST", "SQuAD", "GLUE", "SuperGLUE", "MMLU", "POPE", "CHAIR", "VQA",
    "MIMIC-III", "MIMIC-IV", "UK Biobank", "PubMed", "WMT", "LibriSpeech", "Common Voice", "Kinetics", "KITTI", "Cityscapes",
    "nuScenes", "HumanEval", "GSM8K", "TruthfulQA", "HellaSwag", "Natural Questions", "MS MARCO", "BEIR", "CheXpert",
    "FaceForensics++", "Celeb-DF", "DFDC", "WikiText", "IMDB", "Amazon Reviews", "Yelp", "MovieLens",
]

LEXICONS: dict[str, dict[str, list[str]]] = {
    "method": METHODS, "task": TASKS, "domain": DOMAINS, "population": POPULATIONS, "language": LANGUAGES, "metric": METRICS,
}
CASE_SENSITIVE_ALIASES = {"map", "qa", "ner", "rct", "gan", "vae", "asr", "rag", "roc"}  # short words that are also common English

SENTENCE = re.compile(r"(?<=[.!?])\s+")
DATASET_PATTERN = re.compile(r"\b((?:[A-Z][\w\-+]*|\d+[\w\-]*)(?:\s+[A-Z0-9][\w\-+]*){0,3})\s+(?:dataset|benchmark|corpus|database)\b")


@dataclass
class FacetHit:
    kind: str
    label: str
    sentence: str


@dataclass
class PaperFacets:
    paper_id: str
    hits: dict[str, dict[str, str]] = field(default_factory=dict)  # kind -> label -> evidence sentence

    def labels(self, kind: str) -> set[str]:
        return set(self.hits.get(kind, {}))

    def add(self, kind: str, label: str, sentence: str) -> None:
        self.hits.setdefault(kind, {}).setdefault(label, sentence.strip()[:400])


def _compile(aliases: Iterable[str]) -> list[tuple[re.Pattern[str], bool]]:
    patterns = []
    for alias in aliases:
        sensitive = alias in CASE_SENSITIVE_ALIASES
        word = re.escape(alias.upper() if sensitive else alias)
        patterns.append((re.compile(rf"(?<![\w-]){word}(?![\w-])", 0 if sensitive else re.IGNORECASE), sensitive))
    return patterns


_COMPILED = {kind: {label: _compile([label.lower(), *aliases]) for label, aliases in lexicon.items()} for kind, lexicon in LEXICONS.items()}
_DATASETS = [(name, re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.IGNORECASE)) for name in KNOWN_DATASETS]
_DATASET_ALIASES = {"mscoco": "COCO", "ms coco": "COCO"}
_GENERIC_DATASET_WORDS = {"this", "our", "the", "a", "new", "large", "public", "benchmark", "proposed", "we", "real", "synthetic", "existing", "same", "different", "standard", "two", "three", "several"}


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE.split(re.sub(r"\s+", " ", text or "")) if part.strip()]


def normalize_dataset(name: str) -> str | None:
    clean = re.sub(r"\s+", " ", name).strip(" .,;:()[]")
    if not clean or len(clean) < 2 or len(clean) > 60:
        return None
    words = clean.split(" ")
    while words and words[0].lower() in _GENERIC_DATASET_WORDS:
        words = words[1:]
    if not words:
        return None
    clean = " ".join(words)
    known = next((known for known in KNOWN_DATASETS if known.lower() == clean.lower()), None)
    return _DATASET_ALIASES.get(clean.lower(), known or clean)


def extract(paper_id: str, title: str, abstract: str | None, *, datasets: Iterable[str] = (), methods: Iterable[str] = (), include_limitations: bool = False) -> PaperFacets:
    """Facets a paper actually studies. Contexts named only in a limitation / future-work sentence ("future work should
    study children") are not counted as studied — they are evidence of absence, used by the limitation signal instead."""
    facets = PaperFacets(paper_id=paper_id)
    parts = [title, *sentences(abstract or "")]
    for sentence in parts:
        limitation = not include_limitations and bool(LIMITATION.search(sentence))
        for kind, labels in _COMPILED.items():
            if limitation and kind != "method":
                continue
            for label, patterns in labels.items():
                if any(pattern.search(sentence) for pattern, _ in patterns):
                    facets.add(kind, label, sentence)
        for name, pattern in _DATASETS:
            if pattern.search(sentence):
                facets.add("dataset", _DATASET_ALIASES.get(name.lower(), name), sentence)
        for match in ([] if limitation else DATASET_PATTERN.finditer(sentence)):
            label = normalize_dataset(match.group(1))
            if label and not any(label.lower() == method.lower() for method in METHODS):
                facets.add("dataset", label, sentence)
    for value in datasets:
        label = normalize_dataset(str(value))
        if label:
            facets.add("dataset", label, title)
    for value in methods:
        text = str(value).strip()
        match = next((label for label, patterns in _COMPILED["method"].items() if any(pattern.search(text) for pattern, _ in patterns)), None)
        if match:
            facets.add("method", match, title)
    return facets


LIMITATION = re.compile(
    r"\b(limitation|limitations|limited to|only (?:evaluated|tested|considered|focus(?:ed)?)|future work|remains? (?:unexplored|open|unclear)|"
    r"not (?:yet )?(?:been )?(?:studied|evaluated|explored|tested|addressed)|lack of|lacks|small sample|further research|is needed|are needed)\b",
    re.IGNORECASE,
)
STOP = set("""a an the and or of to in on for with without by from at as is are was were be been being this that these those it its our we
their they them which who whom whose what when where how than then also such may might can could should would will not no nor only
more most less least very further future work works limitation limitations limited study studies paper papers research needed need
remains remain open unclear lack lacks small sample evaluated tested explored addressed studied approach approaches method methods
model models results result data using used use based however while both other new proposed present into over under between across
within one two three first second however""".split())


def limitation_sentences(abstract: str | None) -> list[str]:
    return [sentence for sentence in sentences(abstract or "") if LIMITATION.search(sentence)]


def key_terms(sentence: str) -> set[str]:
    words = re.findall(r"[a-z][a-z\-]{3,}", sentence.lower())
    return {word.rstrip("s") for word in words if word not in STOP}
