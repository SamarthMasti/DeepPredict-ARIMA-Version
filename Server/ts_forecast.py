# ts_forecast.py
import pandas as pd
import numpy as np
import os

# Try import ARIMA; if statsmodels not available we'll fallback to naive forecast
try:
    from statsmodels.tsa.arima.model import ARIMA
    _HAS_ARIMA = True
except Exception:
    ARIMA = None
    _HAS_ARIMA = False

_hpi_series = None
_model_fit = None


def load_hpi_and_fit(csv_path='artifacts/bangalore_hpi.csv', arima_order=(1, 1, 1)):
    """
    Load HPI CSV and fit ARIMA (if available).
    Accepts CSV with columns like: Date,HPI  (Date examples: Mar-17, Jun-17, ...)
    or Quarter,ALL. It detects 'Date' or 'Quarter', and 'HPI' or 'ALL'.
    """
    global _hpi_series, _model_fit

    base = os.path.dirname(__file__)
    path = os.path.join(base, csv_path) if not os.path.isabs(csv_path) else csv_path

    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV not found at {path}")

    df = pd.read_csv(path)

    # detect date column
    if 'Quarter' in df.columns:
        date_col = 'Quarter'
        date_format = '%b-%y'  # e.g., Mar-17
    elif 'Date' in df.columns:
        date_col = 'Date'
        date_format = '%b-%y'  # try same format first
    else:
        raise KeyError("CSV must contain 'Quarter' or 'Date' column")

    # convert to datetime robustly (strip whitespace)
    df[date_col] = df[date_col].astype(str).str.strip()
    parsed = pd.to_datetime(df[date_col], format=date_format, errors='coerce')

    # if parsing failed (NaT), try a more flexible parse
    if parsed.isna().any():
        parsed = pd.to_datetime(df[date_col], errors='coerce')

    df[date_col] = parsed
    df = df.dropna(subset=[date_col]).copy()
    df = df.sort_values(date_col)
    df.set_index(date_col, inplace=True)

    # detect HPI column
    if 'ALL' in df.columns:
        hpi_col = 'ALL'
    elif 'HPI' in df.columns:
        hpi_col = 'HPI'
    else:
        # try to find a numeric column by heuristics
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if len(numeric_cols) >= 1:
            hpi_col = numeric_cols[0]
        else:
            raise KeyError("CSV must contain 'ALL' or 'HPI' or at least one numeric column")

    _hpi_series = df[hpi_col].astype(float)

    # force quarterly frequency (convert timestamps into quarter-end timestamps)
    try:
        _hpi_series.index = pd.DatetimeIndex(_hpi_series.index).to_period('Q').to_timestamp('Q')
    except Exception:
        # fallback: simply sort and keep timestamps
        _hpi_series = _hpi_series.sort_index()

    # Fit ARIMA if available; otherwise leave _model_fit None (naive fallback)
    if _HAS_ARIMA:
        try:
            model = ARIMA(_hpi_series, order=arima_order)
            _model_fit = model.fit()
        except Exception as e:
            # fitting failed; warn and use fallback
            _model_fit = None
            print("Warning: ARIMA fit failed — falling back to naive forecasting. Error:", e)
    else:
        _model_fit = None
        print("Warning: statsmodels ARIMA not available — falling back to naive forecasting.")

    print("✅ HPI series loaded. Points:", len(_hpi_series))
    return True


def forecast_hpi(steps=4):
    """
    Forecast next `steps` quarters.
    Returns (forecast_series (pd.Series), conf_int (pd.DataFrame or None))
    If ARIMA not available, returns naive forecast repeating last observed value.
    """
    global _model_fit, _hpi_series
    if _hpi_series is None:
        raise RuntimeError("HPI series not loaded. Call load_hpi_and_fit() first.")

    if _model_fit is not None:
        res = _model_fit.get_forecast(steps=steps)
        forecast = res.predicted_mean
        conf_int = res.conf_int()
    else:
        last = float(_hpi_series.iloc[-1])
        forecast = pd.Series([last] * steps)
        conf_int = None

    # create quarterly index starting next quarter-end after last_date
    last_date = _hpi_series.index[-1]
    try:
        # the series index is quarter-end timestamps; next quarter-end:
        next_q_end = last_date + pd.offsets.QuarterEnd()
        forecast_index = pd.date_range(start=next_q_end, periods=steps, freq='Q')
    except Exception:
        # fallback monthly to be safe
        forecast_index = pd.date_range(start=last_date + pd.offsets.MonthEnd(1), periods=steps, freq='M')

    forecast.index = forecast_index
    if conf_int is not None:
        try:
            conf_int.index = forecast_index
        except Exception:
            pass

    return forecast, conf_int


def get_market_forecast_summary(steps=4):
    """
    Returns (growth_rate, volatility, risk_label, forecast_series)
    - growth_rate is fraction (e.g., 0.05 for 5% total growth over `steps`)
    - volatility is std of historical pct changes
    - risk_label is "Low"/"Moderate"/"High"
    """
    global _hpi_series
    if _hpi_series is None:
        # safe fallback: no HPI loaded
        return 0.0, 0.0, "Moderate", None

    try:
        forecast, _ = forecast_hpi(steps=steps)
        last_hist = float(_hpi_series.iloc[-1])
        last_fore = float(forecast.iloc[-1])
        growth_rate = (last_fore - last_hist) / last_hist if last_hist != 0 else 0.0

        returns = _hpi_series.pct_change().dropna()
        volatility = float(returns.std()) if len(returns) > 0 else 0.0

        if growth_rate > 0.05 and volatility < 0.02:
            risk = "Low"
        elif growth_rate > -0.02:
            risk = "Moderate"
        else:
            risk = "High"

        return float(growth_rate), float(volatility), risk, forecast

    except Exception as e:
        print("ts_forecast.get_market_forecast_summary error:", e)
        return 0.0, 0.0, "Moderate", None


# simple CLI test
if __name__ == "__main__":
    load_hpi_and_fit()
    gr, vol, rsk, f = get_market_forecast_summary(steps=4)
    print("growth", gr, "vol", vol, "risk", rsk)
    if f is not None:
        print(f)
