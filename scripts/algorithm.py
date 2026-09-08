import json, time
import requests

# Fill these in with the URLs the organizer gave you when they registered you:
MARKET_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/main/docs/data/market.json"
HOLDINGS_URL = "http://raw.githubusercontent.com/exofri/ensim-trade-center/main/traders/tester/holdings.json"

WINDOW = 20            # rolling window for the moving average / std dev
K = 1.5                # number of standard deviations for the bands
SIGNAL_SCALE = 3       # how many "std devs past the band" maps to a full +-1 decision
MIN_MONEY_RESERVE = 50 # never let a buy signal spend below this much money

def fetch_json(url):
    resp = requests.get(url, proxies={"http": None, "https": None}, timeout=(10, 20))
    resp.raise_for_status()
    return resp.json()

def bollinger_signal(prices, window=WINDOW, k=K):
    # Not enough history yet -- hold rather than guess from noise.
    if len(prices) < window:
        return 0.0
    recent = prices[-window:]
    mean = sum(recent) / len(recent)
    variance = sum((p - mean) ** 2 for p in recent) / len(recent)
    std = variance ** 0.5
    if std == 0:
        return 0.0
    upper = mean + k * std
    lower = mean - k * std
    price = prices[-1]
    if price < lower:
        # Below the lower band -- price is unusually low relative to its recent
        # range, a simple mean-reversion read says "buy". Distance past the band
        # (in std devs) scales the signal strength, clipped to [-1, 1].
        return max(0.0, min(1.0, (lower - price) / (std * SIGNAL_SCALE)))
    elif price > upper:
        return -max(0.0, min(1.0, (price - upper) / (std * SIGNAL_SCALE)))
    return 0.0

def apply_budget_guard(raw_signal, money, price, reserve=MIN_MONEY_RESERVE):
    # A buy signal (positive) that would spend into the reserve gets scaled down,
    # not silently zeroed out -- you still act on the signal, just smaller. A sell
    # signal is never touched here: selling only ever adds money, never risks it.
    if raw_signal <= 0:
        return raw_signal
    if money <= reserve:
        return 0.0
    max_affordable_units = (money - reserve) / price
    desired_units = 100 * raw_signal
    if desired_units <= max_affordable_units:
        return raw_signal
    return round(max_affordable_units / 100, 3)

def main():
    market = fetch_json(MARKET_URL)
    holdings = fetch_json(HOLDINGS_URL)
    products = market["products"]
    history = market["history"]

    decision = {}
    for p in products:
        prices = [row[p] for row in history]
        raw = bollinger_signal(prices)
        current_price = prices[-1] if prices else 0
        decision[p] = round(apply_budget_guard(raw, holdings["money"], current_price), 3)

    decision["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("decision.json", "w") as f:
        json.dump(decision, f, indent=2)
    print(f"Wrote decision.json: {decision}")

if __name__ == "__main__":
    main()
