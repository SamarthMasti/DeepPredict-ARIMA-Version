// app.js - updated (no Chart.js)
const API_BASE = "http://127.0.0.1:5000";

function getBathValue() {
  var uiBathrooms = document.getElementsByName("uiBathrooms");
  for (var i = 0; i < uiBathrooms.length; i++) {
    if (uiBathrooms[i].checked) {
      return parseInt(uiBathrooms[i].value);
    }
  }
  return -1;
}

function getBHKValue() {
  var uiBHK = document.getElementsByName("uiBHK");
  for (var i = 0; i < uiBHK.length; i++) {
    if (uiBHK[i].checked) {
      return parseInt(uiBHK[i].value);
    }
  }
  return -1;
}

function onPageLoad() {
  console.log("document loaded");
  const url = `${API_BASE}/get_location_names`;
  $.get(url, function (data, status) {
    console.log("got response for get_location_names request");
    if (data && data.locations) {
      const locations = data.locations;
      const uiLocations = document.getElementById("uiLocations");
      uiLocations.innerHTML = "";
      // Add placeholder
      const placeholder = document.createElement("option");
      placeholder.disabled = true;
      placeholder.selected = true;
      placeholder.textContent = "Choose a Location";
      uiLocations.appendChild(placeholder);

      locations.forEach(function (loc) {
        const opt = document.createElement("option");
        opt.value = loc;
        opt.textContent = loc;
        uiLocations.appendChild(opt);
      });
    } else {
      console.warn("No locations received");
      const uiLocations = document.getElementById("uiLocations");
      uiLocations.innerHTML = "<option disabled selected>Unable to load locations</option>";
    }
  }).fail(function (xhr, status, err) {
    console.error("Error fetching locations:", err);
    const uiLocations = document.getElementById("uiLocations");
    uiLocations.innerHTML = "<option disabled selected>Unable to load locations</option>";
  });
}

function formatCurrency(val) {
  if (val === null || val === undefined) return "—";
  const n = Number(val);
  if (isNaN(n)) return val;
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

function updateSentimentGauge(score, sentimentLabel) {
  // score expected 0..100
  const gaugeInner = document.getElementById("sentimentGauge");
  const pointer = document.getElementById("gaugePointer");
  const text = document.getElementById("sentimentText");
  const scoreText = document.getElementById("sentimentScore");

  // clamp
  let s = Number(score);
  if (isNaN(s)) s = 50;
  s = Math.min(100, Math.max(0, s));

  // Map 0..100 to -90deg..+90deg pointer rotation
  const rotation = (s / 100) * 180 - 90; // -90..+90
  pointer.style.transform = `translateX(-50%) rotate(${rotation}deg)`;

  // color by label
  let color = "#22c55e"; // green
  if (String(sentimentLabel).toLowerCase().includes("neg")) color = "#ef4444";
  else if (String(sentimentLabel).toLowerCase().includes("neutral")) color = "#f59e0b";

  gaugeInner.style.borderColor = color;
  text.innerText = sentimentLabel || "—";
  scoreText.innerText = `Score: ${s.toFixed(1)}%`;
}

// handle Estimate & Forecast
async function onEstimateClicked() {
  const sqft = parseFloat(document.getElementById("uiSqft").value || 0);
  const bhk = getBHKValue();
  const bath = getBathValue();
  const location = document.getElementById("uiLocations").value;
  const horizon = parseInt(document.getElementById("uiHorizon").value || 12);

  if (!sqft || sqft <= 0) { alert("Enter a valid area (sqft)."); return; }
  if (!location) { alert("Choose a location."); return; }

  document.getElementById("uiEstimatedCurrent").textContent = "Calculating...";
  document.getElementById("uiEstimatedFuture").textContent = "Forecasting...";
  document.getElementById("riskLevel").textContent = "…";
  document.getElementById("riskCategory").textContent = "…";
  document.getElementById("riskMsg").textContent = "";
  document.getElementById("prescription").textContent = "";
  document.getElementById("prescriptionExplain").textContent = "";
  document.getElementById("compositeScore").textContent = "…";

  try {
    // current
    const currentResp = await new Promise((resolve, reject) => {
      $.post(`${API_BASE}/predict_home_price`, {
        total_sqft: sqft,
        bhk: bhk,
        bath: bath,
        location: location
      }, function (data, status) { resolve(data); }).fail((xhr, status, err) => reject(err));
    });

    const current_price = Number(currentResp.estimated_price);
    document.getElementById("uiEstimatedCurrent").textContent = "₹(in lakhs) " + formatCurrency(current_price);

    // future & risk
    const futureResp = await new Promise((resolve, reject) => {
      $.ajax({
        url: `${API_BASE}/predict_future_price`,
        method: "POST",
        contentType: "application/json",
        data: JSON.stringify({
          total_sqft: sqft,
          bhk: bhk,
          bath: bath,
          location: location,
          horizon_months: horizon
        }),
        success: function (data) { resolve(data); },
        error: function (xhr, status, err) { reject(err || status); }
      });
    });

    // extract fields (compatibility fallbacks)
    const future_price = Number(futureResp.future_price || futureResp.expected_price || 0);
    const growth = futureResp.expected_growth_percent;
    const volatility = futureResp.volatility;
    const riskLevel = futureResp.risk_level || futureResp.market_risk || futureResp.risk || "—";
    const compositeScore = futureResp.composite_risk_score ?? futureResp.compositeScore ?? "—";
    const category = futureResp.risk_category ?? "—";
    const msg = futureResp.risk_message ?? "";
    const recommendation = futureResp.recommendation ?? futureResp.recommendation ?? "—";
    const presc = futureResp.prescription_explanation ?? futureResp.prescriptionExplain ?? "";

    document.getElementById("uiEstimatedFuture").textContent = "₹(in lakhs) " + formatCurrency(future_price);
    document.getElementById("riskLevel").textContent = riskLevel;
    document.getElementById("compositeScore").textContent = compositeScore;
    document.getElementById("riskCategory").textContent = category;
    document.getElementById("riskMsg").textContent = msg;
    document.getElementById("prescription").textContent = recommendation;
    document.getElementById("prescriptionExplain").textContent = presc;

    // pill color
    const pill = document.getElementById("riskLevel");
    pill.classList.remove("low", "mod", "high");
    if (String(riskLevel).toLowerCase() === "low") { pill.style.background = "rgba(16,185,129,0.12)"; pill.style.color = "#059669"; }
    else if (String(riskLevel).toLowerCase() === "moderate") { pill.style.background = "rgba(245,158,11,0.12)"; pill.style.color = "#92400e"; }
    else { pill.style.background = "rgba(239,68,68,0.12)"; pill.style.color = "#b91c1c"; }

    // update sentiment gauge if returned
    const sent_label = futureResp.sentiment_label || futureResp.sentiment || null;
    const sent_score = futureResp.sentiment_score ?? futureResp.sentiment_score ?? null;
    if (sent_label || sent_score !== null) {
      updateSentimentGauge(sent_score ?? 50, sent_label ?? "Neutral");
    } else {
      updateSentimentGauge(50, "Neutral");
    }

  } catch (err) {
    console.error("Error during estimate:", err);
    alert("Error obtaining prediction: " + (err?.toString?.() || err));
    document.getElementById("uiEstimatedCurrent").textContent = "—";
    document.getElementById("uiEstimatedFuture").textContent = "—";
  }
}

function onReset() {
  document.getElementById("uiSqft").value = 1000;
  document.getElementById("uiHorizon").value = 12;
  const loc = document.getElementById("uiLocations");
  if (loc.options.length > 0) loc.selectedIndex = 0;
  // reset results
  document.getElementById("uiEstimatedCurrent").textContent = "—";
  document.getElementById("uiEstimatedFuture").textContent = "—";
  document.getElementById("riskLevel").textContent = "—";
  document.getElementById("compositeScore").textContent = "—";
  document.getElementById("riskCategory").textContent = "—";
  document.getElementById("riskMsg").textContent = "";
  document.getElementById("prescription").textContent = "";
  document.getElementById("prescriptionExplain").textContent = "";
  updateSentimentGauge(50, "Neutral");
}

window.onload = function() {
  onPageLoad();
  document.getElementById("estimateBtn").addEventListener("click", onEstimateClicked);
  document.getElementById("resetBtn").addEventListener("click", onReset);
  document.getElementById("analyzeBtn").addEventListener("click", async function(){
    const userInput = document.getElementById("userText").value;
    if(!userInput || userInput.trim()===""){ alert("Enter text to analyze"); return; }
    try {
      const resp = await fetch(`${API_BASE}/analyze_sentiment`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ text: userInput })
      });
      const result = await resp.json();
      // result may have different shape depending on server; handle common cases
      const label = result.sentiment || result.sentiment_label || result.sentimentLabel || result.label || "Neutral";
      const score = result.score ?? result.confidence ?? result.sentiment_score ?? 0;
      document.getElementById("sentimentResult").innerHTML = `Sentiment: <b>${label}</b> • Confidence: ${Number(score).toFixed(2)}%`;
      updateSentimentGauge(Number(score) || 50, label);
    } catch (e) {
      console.error("Sentiment analyze failed", e);
      alert("Sentiment analyze failed: " + e);
    }
  });
};
