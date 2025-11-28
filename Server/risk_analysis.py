# risk_analysis.py
import numpy as np

def analyze_risk(current_price, growth_rate, volatility,
                 sentiment_label="Neutral", sentiment_score=50.0,
                 location_factor=1.0):
    """
    Composite risk: price + forecast (growth/volatility) + sentiment + location.
    - current_price: numeric (expected in lakhs; if in rupees, convert before calling)
    - growth_rate: fractional (0.05 = +5%)
    - volatility: fractional (std of pct changes)
    - sentiment_label: "Positive"/"Neutral"/"Negative"
    - sentiment_score: 0..100 (RoBERTa score)
    - location_factor: >1 safer, <1 riskier
    Returns:
      {
        "score": float(0..100),
        "level": "Low"/"Moderate"/"High",
        "category": str,
        "message": str,
        "debug": {...}
      }
    """

    # ---------------------------
    # 1) Market component (unchanged)
    # ---------------------------
    gr_pct = float(growth_rate) * 100.0
    vol_pct = float(volatility) * 100.0

    # keep your original market component formula
    market_component = (vol_pct * 1.5) - (gr_pct * 0.8)

    # location adjustment (your earlier multiplier)
    adjusted_market = market_component * (1.2 - float(location_factor))

    # clip to 0..100
    market_risk_score = float(np.clip(adjusted_market, 0.0, 100.0))

    # market risk level numeric mapping: 1 low, 2 med, 3 high
    if market_risk_score < 30:
        market_risk_level = 1
    elif market_risk_score < 60:
        market_risk_level = 2
    else:
        market_risk_level = 3

    # ---------------------------
    # 2) Sentiment component
    # ---------------------------
    sent = (sentiment_label or "Neutral").strip().lower()
    s_score = float(sentiment_score or 50.0)  # 0..100

    # sentiment numeric risk mapping (1 low .. 3 high)
    # Positive + high score -> low risk; Negative or very low score -> high risk
    if (sent == "positive" and s_score >= 60):
        sentiment_risk_level = 1
    elif (sent == "negative" or s_score < 40):
        sentiment_risk_level = 3
    else:
        sentiment_risk_level = 2

    # For numeric sentiment contribution we convert positivity -> lower risk.
    # We'll define sentiment_numeric: lower means safer.
    # Map s_score (0..100) -> sentiment_numeric_risk (0..100) where higher is more risky.
    # Simpler: sentiment_numeric_risk = 100 - s_score  (positive -> small risk, negative -> large)
    sentiment_numeric_risk = float(np.clip(100.0 - s_score, 0.0, 100.0))

    # ---------------------------
    # 3) Price component (NEW)
    # ---------------------------
    # current_price expected in lakhs (if in rupees, divide by 1e5 first)
    # We add a small price-driven risk: extremely expensive properties may be slightly riskier.
    # This is intentionally conservative — price should not swamp market+sentiment.
    try:
        cp = float(current_price or 0.0)
    except Exception:
        cp = 0.0

    # simple heuristic:
    #  - cp <= 10 lakhs -> price_risk small (cheap)
    #  - cp around 50 lakhs -> price_risk modest
    #  - cp > 200 lakhs -> price_risk higher
    price_risk_score = np.clip((cp / 200.0) * 100.0, 0.0, 100.0)  # 0..100
    # price_risk_score is small for normal cp values; adjust multiplier above if you want stronger effect

    # ---------------------------
    # 4) Combine components with weights
    # ---------------------------
    # Keep market the dominant signal (70%), sentiment next (20%), price small (10%)
    # These are tunable; kept intentionally similar to prior weighting where market had high weight.
    W_MARKET = 0.70
    W_SENTIMENT = 0.20
    W_PRICE = 0.10

    # final_numeric_score: lower means less risk; we already have market_risk_score (higher = more risk)
    final_numeric_raw = (
        market_risk_score * W_MARKET +
        sentiment_numeric_risk * W_SENTIMENT +
        price_risk_score * W_PRICE
    )

    # normalize / clip
    final_numeric_score = float(np.clip(round(final_numeric_raw, 2), 0.0, 100.0))

    # Convert composite numeric -> final level (same thresholds as before)
    if final_numeric_score < 30:
        level = "Low"
        category = "Stable Market"
        message = "Strong signals with low volatility. Good investment conditions."
    elif final_numeric_score < 60:
        level = "Moderate"
        category = "Caution Advised"
        message = "Some mixed signals. Consider cautious investment."
    else:
        level = "High"
        category = "High Risk"
        message = "Negative sentiment or high volatility. Avoid large investments."

    # debug info to trace internals (very useful in UI)
    debug = {
        "market_risk_score": market_risk_score,
        "market_risk_level": market_risk_level,
        "sentiment_label": sentiment_label,
        "sentiment_score": s_score,
        "sentiment_numeric_risk": sentiment_numeric_risk,
        "sentiment_risk_level": sentiment_risk_level,
        "price_risk_score": price_risk_score,
        "weights": {"market": W_MARKET, "sentiment": W_SENTIMENT, "price": W_PRICE},
        "final_raw": final_numeric_raw
    }

    return {
        "score": final_numeric_score,
        "level": level,
        "category": category,
        "message": message,
        "debug": debug
    }


def get_prescription(risk_score, growth_rate):
    """Prescriptive engine similar to your earlier version."""
    roi_pct = round(growth_rate * 100.0, 2)

    if risk_score < 30 and roi_pct > 3:
        action = "Buy"
        explanation = f"Low risk and strong expected growth ({roi_pct}%)."
    elif risk_score < 60 and roi_pct > 0:
        action = "Hold"
        explanation = f"Moderate risk with mild positive growth ({roi_pct}%)."
    elif roi_pct < 0:
        action = "Sell"
        explanation = f"Negative growth forecast ({roi_pct}%). High caution."
    else:
        action = "Wait"
        explanation = f"No clear signal (risk {risk_score}, expected {roi_pct}%)."

    return {
        "action": action,
        "explanation": explanation
    }
