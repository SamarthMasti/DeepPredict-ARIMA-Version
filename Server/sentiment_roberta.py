# sentiment_roberta.py
"""
RoBERTa sentiment integration.
- Uses Hugging Face transformers pipeline with `cardiffnlp/twitter-roberta-base-sentiment`
- Fetches live headlines via NewsAPI (if NEWSAPI_KEY provided) and aggregates
- Provides functions:
    get_sentiment_for_topic(topic, top_k=10) -> (label, score_percent, details)
    analyze_text(text) -> (label, score_percent)
"""
# server.py (top of file)


import os
import time
import requests
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from collections import Counter
from math import floor

# Choose model (cardiffnlp is good for short headlines / social)
HF_MODEL = os.environ.get("SENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment")
# You can switch to "distilbert-base-uncased-finetuned-sst-2-english" if you prefer.

# Lazy-init pipeline (so import is cheap)
_pipeline = None
_last_init = 0
_INIT_COOLDOWN = 1  # seconds


def _init_pipeline():
    global _pipeline, _last_init
    if _pipeline is None:
        # create pipeline (this will download model the first time)
        _pipeline = pipeline("sentiment-analysis", model=HF_MODEL, device=-1)
        _last_init = time.time()
    return _pipeline


def _fetch_newsapi_headlines(query, api_key=None, page_size=20):
    """
    Fetch headlines from NewsAPI. Returns list of title strings.
    api_key: if None, looks for NEWSAPI_KEY env var.
    """
    key = api_key or os.environ.get("NEWSAPI_KEY")
    if not key:
        return []  # no api key — caller should handle fallback

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "pageSize": page_size,
        "sortBy": "publishedAt",
        "apiKey": key
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        j = r.json()
        items = j.get("articles", [])
        headlines = [it.get("title", "") for it in items if it.get("title")]
        return headlines
    except Exception:
        return []


# sentiment_roberta.py (replace or update file)
import os, time, requests
from transformers import pipeline
from collections import Counter

HF_MODEL = os.environ.get("SENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment")
_pipeline = None

def _init_pipeline():
    global _pipeline
    if _pipeline is None:
        # cpu device by default; set device=0 for GPU
        _pipeline = pipeline("sentiment-analysis", model=HF_MODEL, device=-1)
    return _pipeline

def analyze_text(text):
    """
    Analyze single text. Returns a dict:
      { 'sentiment': 'Positive'|'Neutral'|'Negative', 'score': float(0..100), 'raw': {...} }
    Always returns numeric score in 0..100 scale.
    """
    if not text or not str(text).strip():
        return {'sentiment': 'Neutral', 'score': 50.0, 'raw': {'reason': 'empty_input'}}

    pipe = _init_pipeline()
    try:
        out = pipe(text[:1000])  # list of results
        if not out or not isinstance(out, list):
            return {'sentiment': 'Neutral', 'score': 50.0, 'raw': {'reason': 'no_output'}}

        r = out[0]
        raw_label = r.get('label', '')
        raw_score = float(r.get('score', 0.0))

        lab = str(raw_label).lower()

        # Map label to Positive/Neutral/Negative robustly
        if lab in ("positive", "pos", "label_2", "label2", "LABEL_2".lower()):
            sentiment = "Positive"
            score_pct = raw_score * 100.0
        elif lab in ("negative", "neg", "label_0", "label0", "LABEL_0".lower()):
            sentiment = "Negative"
            # convert model's confidence (score) to "positivity" percentage (so 0..100)
            # for negative, we invert to give a "positive strength" measure if needed.
            score_pct = (1.0 - raw_score) * 100.0
        elif lab in ("neutral","neu" "label1"):
            sentiment = "Neutral"
            score_pct = raw_score * 100.0
        else:
            # fallback: try substring check
            if "pos" in lab:
                sentiment = "Positive"; score_pct = raw_score * 100.0
            elif "neg" in lab:
                sentiment = "Negative"; score_pct = (1.0 - raw_score) * 100.0
            else:
                sentiment = "Neutral"; score_pct = raw_score * 100.0

        score_pct = max(0.0, min(100.0, round(score_pct, 2)))

        return {'sentiment': sentiment, 'score': score_pct, 'raw': r}
    except Exception as e:
        return {'sentiment': 'Neutral', 'score': 50.0, 'raw': {'error': str(e)}}


def aggregate_headlines_sentiment(headlines, chunk_size=8):
    """
    Given a list of headline strings, run sentiment analysis per headline,
    aggregate by averaging positive scores and majority label.
    Returns: (label, avg_percent, details)
    """
    if not headlines:
        return ("Neutral", 50.0, {"count": 0})

    pipe = _init_pipeline()
    results = []
    # The pipeline can accept a list
    try:
        # Keep length manageable
        sample = headlines[:chunk_size]
        res = pipe(sample)
        pos_scores = []
        labels = []
        for r in res:
            labs = r.get("label", "").lower()
            score = r.get("score", 0.0)
            if "pos" in labs:
                labels.append("Positive")
                pos_scores.append(score)
            elif "neu" in labs:
                labels.append("Neutral")
                pos_scores.append(score * 0.5)  # neutral less weight
            elif "neg" in labs:
                labels.append("Negative")
                pos_scores.append(1 - score)  # invert negative for overall positivity
            else:
                labels.append(r.get("label", "Neutral"))
                pos_scores.append(0.5)
        # majority label
        most = Counter(labels).most_common(1)[0][0]
        # average score_percent (scale to 0..100)
        avg_score = float(sum(pos_scores) / max(1, len(pos_scores))) * 100.0
        avg_score = round(avg_score, 2)
        return (most, avg_score, {"count": len(sample), "labels": labels})
    except Exception:
        return ("Neutral", 50.0, {"count": 0})


def get_sentiment_for_topic(topic, newsapi_key=None, fallback_text=None):
    """
    Main helper: tries to fetch headlines for `topic` via NewsAPI, analyzes them,
    returns (label, score_percent, details).
    - If NewsAPI key is missing or fetch fails: uses fallback_text if provided.
    """
    headlines = _fetch_newsapi_headlines(topic, api_key=newsapi_key, page_size=20)
    if headlines:
        return aggregate_headlines_sentiment(headlines)
    # fallback: analyze the fallback_text if given
    if fallback_text:
        return analyze_text(fallback_text)
    # final fallback
    return ("Neutral", 50.0, {"reason": "no_data"})
