# server.py
from flask import Flask, request, jsonify
import util
import ts_forecast
import traceback
import risk_analysis
import math
from flask_cors import CORS


from sentiment_roberta import analyze_text, get_sentiment_for_topic


app = Flask(__name__)
CORS(app)
# ----- Startup: load model & HPI forecast model once -----
try:
    util.load_saved_artifacts()
except Exception as e:
    print("Error loading artifacts in util.py:", e)
    traceback.print_exc()
    raise

# Fit ARIMA on HPI (this may take a few seconds). If it fails, ts_forecast will fallback.
try:
    ts_forecast.load_hpi_and_fit(csv_path='artifacts/bangalore_hpi.csv', arima_order=(1, 1, 1))
    print("HPI ARIMA model loaded (or fallback in place).")
except Exception as e:
    print("Warning: ARIMA model not fitted at startup:", e)
    traceback.print_exc()

# ----- API endpoints -----
@app.route('/get_location_names')
def get_location_names():
    try:
        response = jsonify({'locations': util.get_location_names()})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/predict_home_price', methods=['POST'])
def predict_home_price():
    try:
        data = request.form if request.form else request.get_json(force=True)
        total_sqft = float(data.get('total_sqft'))
        location = data.get('location')
        bhk = int(data.get('bhk'))
        bath = int(data.get('bath'))

        current_price = util.get_estimated_price(location, total_sqft, bhk, bath)
        response = jsonify({'estimated_price': current_price})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        print("predict_home_price error:", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# inside server.py (replace your analyze_sentiment route)
@app.route('/analyze_sentiment', methods=['POST'])
def analyze_sentiment_route():
    try:
        data = request.form if request.form else request.get_json(force=True)
        text = (data.get('text') or "").strip()
        if not text:
            return jsonify({'sentiment': 'Neutral', 'score': 50.0, 'error': 'no_text_provided'}), 400

        result = analyze_text(text)
        # ensure keys exist
        sentiment = result.get('sentiment', 'Neutral')
        score = result.get('score', 50.0)
        raw = result.get('raw', {})
        resp = {'sentiment': sentiment, 'score': score, 'raw': raw}
        resp_json = jsonify(resp)
        resp_json.headers.add('Access-Control-Allow-Origin', '*')
        return resp_json
    except Exception as e:
        print("analyze_sentiment_route error:", e)
        return jsonify({'sentiment': 'Neutral', 'score': 50.0, 'error': str(e)}), 500



# (inside server.py) -- replace existing predict_future_price with this
import math
import traceback
from flask import jsonify, request

@app.route('/predict_future_price', methods=['POST'])
def predict_future_price():
    print("✅ Received request for future price prediction")
    try:
        data = request.form if request.form else request.get_json(force=True)
        print("🧩 Data received:", data)

        # parse & validate inputs
        total_sqft = float(data.get('total_sqft', 0))
        location = (data.get('location') or "").strip()
        bhk = int(data.get('bhk', 0))
        bath = int(data.get('bath', 0))
        horizon_months = int(data.get('horizon_months', 12))

        print(f"✅ Inputs parsed: sqft={total_sqft}, location={location}, bhk={bhk}, bath={bath}, horizon={horizon_months}")

        # 1) current price from XGBoost util
        current_price = util.get_estimated_price(location, total_sqft, bhk, bath)
        print("💰 Current price predicted:", current_price)

        # 2) convert months to quarters for the HPI (quarterly) series
        quarters = max(1, math.ceil(horizon_months / 3.0))
        print("➡ quarters to forecast:", quarters)

        # 3) ARIMA market forecast
        try:
            growth_rate, volatility, market_risk_label, forecast_series = ts_forecast.get_market_forecast_summary(steps=quarters)
            print("📈 Forecast summary:", growth_rate, volatility, market_risk_label)
        except Exception as ar_e:
            # fallback values when ts_forecast fails
            print("⚠️ ts_forecast failed:", ar_e)
            traceback.print_exc()
            growth_rate, volatility, market_risk_label, forecast_series = 0.03, 0.02, "Moderate", None

        # 4) future price computation
        future_price = current_price * (1 + growth_rate)
        print("🔮 Future price computed:", future_price)

        # 5) location factor heuristic
        location_factor = 1.0
        if isinstance(location, str):
            loc_lower = location.lower()
            if 'indira' in loc_lower:
                location_factor = 1.1
            elif 'whitefield' in loc_lower:
                location_factor = 0.95
            elif 'jp nagar' in loc_lower:
                location_factor = 1.02
        print("📍 Location factor:", location_factor)

        # 6) risk analysis + prescription
        # try to get user text
        data = request.get_json(force=True)
        text = (data.get("text") or "").strip()

        # CASE 1: user provided text
        if text:
            sentiment = risk_analysis.analyze_text(text)

            # CASE 2: no text → try news sentiment
        else:
            label, score, details = get_sentiment_for_topic("real estate")
            sentiment = {
        "sentiment": label,
        "score": score,
        "raw": details
    }

        risk_result = risk_analysis.analyze_risk(
    current_price,
    growth_rate,
    volatility,
    sentiment_label=sentiment['sentiment'],
    sentiment_score=sentiment['score'],
     location_factor=location_factor
)
        print("⚠️ Risk result:", risk_result)
        prescription = risk_analysis.get_prescription(risk_result['score'], growth_rate)
        print("💊 Prescription:", prescription)
                # 7) Sentiment analysis using RoBERTa model (live or fallback)
        try:
            sent_label, sent_score, sent_details = get_sentiment_for_topic(location)
            print(f"🧠 Sentiment for {location}: {sent_label} ({sent_score}%)")
        except Exception as s_e:
            print("⚠️ Sentiment analysis failed:", s_e)
            sent_label, sent_score, sent_details = "Neutral", 50.0, {"error": str(s_e)}

        # 7) build JSON response
        response = jsonify({
    'current_price': round(current_price, 2),
    'future_price': round(future_price, 2),
    'expected_growth_percent': round(growth_rate * 100, 2),
    'volatility': round(volatility, 4),
    'market_risk': market_risk_label,
    'composite_risk_score': risk_result.get('score'),
    'risk_level': risk_result.get('level'),
    'risk_category': risk_result.get('category'),
    'risk_message': risk_result.get('message'),
    'recommendation': prescription.get('action'),
    'prescription_explanation': prescription.get('explanation'),

    # --- NEW SENTIMENT FIELDS ---
    'sentiment_label': sent_label,
    'sentiment_score': sent_score
})

        response.headers.add('Access-Control-Allow-Origin', '*')
        print("✅ Response ready, sending to client.")
        return response

    except Exception as e:
        print("❌ predict_future_price ERROR:", e)
        traceback.print_exc()
        # Return JSON with error + traceback so frontend can show details
        resp = jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        })
        resp.headers.add('Access-Control-Allow-Origin', '*')
        return resp, 500

if __name__ == "__main__":
    print("Starting server...")
    # run on all interfaces only if you want to access from other machines; local dev default is fine
    app.run(debug=True)
