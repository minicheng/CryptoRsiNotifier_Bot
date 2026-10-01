"""
CoinGecko + CCXT (Bitget) 數據抓取模組
1. 使用 CoinGecko API 依照市值排名篩選前 N 名加密貨幣（排除穩定幣與包裝代幣）
2. 使用 CCXT 連接 Bitget 抓取日 K 線 (OHLCV) 歷史資料（預設 300 根）

快取策略（減少不必要的 API 呼叫）：
- CoinGecko 幣種清單：cache 以「UTC 日期」為 key，當天內重用同一份排名資料
- Bitget 天圖日K：cache 以「UTC 日期 + symbol」為 key，當天內重用（每日只有收盤才更新）
- Bitget 1h / 6h K 線：每次都 fresh fetch（策略條件 2、3、4 需要即時小時資料）
"""

import os
import sys
import json
import time
import datetime
import requests
import ccxt

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from config import (
    COINGECKO_API_URL,
    TOP_N_COINS,
    EXCLUDED_SYMBOLS,
    EXCHANGE_ID,
    DEFAULT_MARKET_TYPE,
    LOOKBACK_BARS,
    LOOKBACK_BARS_1H,
    LOOKBACK_BARS_6H,
    LOOKBACK_BARS_4H,
)

# 快取目錄（GitHub Actions 的 cache action 會持久化此目錄）
CACHE_DIR = os.environ.get("SCANNER_CACHE_DIR", "cache")


def _today_utc() -> str:
    """回傳今天 UTC 日期字串 (YYYY-MM-DD)，作為快取 key"""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _utc_slot(interval_hours: int) -> str:
    """
    回傳目前 UTC 時間處於哪個時段 slot，作為 K 線快取 key。
    例: interval_hours=6 → 0, 1, 2, 3 (slot 每 6 小時翻濠一次)
         interval_hours=4 → 0, 1, 2, 3, 4, 5
    """
    utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
    return str(utc_hour // interval_hours)


def _cache_path(name: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name)


def _load_cache(filename: str):
    """讀取 JSON 快取，若不存在或解析失敗回傳 None"""
    path = _cache_path(filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return None


def _save_cache(filename: str, data) -> None:
    """寫入 JSON 快取"""
    path = _cache_path(filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ 快取寫入失敗 ({filename}): {e}")


def get_exchange():
    """初始化並回傳 CCXT exchange 實例（Bitget USDT-M 永續合約）"""
    exchange_class = getattr(ccxt, EXCHANGE_ID, ccxt.bitget)
    exchange = exchange_class({
        "enableRateLimit": True,
        "timeout": 15000,
        "options": {
            "defaultType": DEFAULT_MARKET_TYPE,  # "swap" 永續合約 (USDT-M Futures)
        },
    })
    return exchange


def fetch_coingecko_candidates(limit=100):
    """
    從 CoinGecko 取得市值排名前列的代幣資料。
    同一天（UTC）內直接從本地 cache 讀取，不重複呼叫 API。
    若 CoinGecko 失敗，自動切換備用資料源 (CoinPaprika)。
    """
    today = _today_utc()
    cache_file = f"coingecko_{today}.json"
    cached = _load_cache(cache_file)
    if cached:
        print(f"✅ 幣種清單快取命中（{today}），略過 CoinGecko API 呼叫")
        return cached

    print("📊 正在向 CoinGecko 查詢加密貨幣市值排名...")
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    cg_api_key = os.environ.get("COINGECKO_API_KEY")
    if cg_api_key:
        headers["x-cg-demo-api-key"] = cg_api_key

    try:
        resp = requests.get(COINGECKO_API_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list):
            _save_cache(cache_file, data)
            return data
    except Exception as e:
        print(f"⚠️ CoinGecko API 請求未成功 ({e})，自動切換至 CoinPaprika 備用源...")

    # 備用源 1: CoinPaprika (無需 Key，穩定開放)
    try:
        resp = requests.get("https://api.coinpaprika.com/v1/tickers?quotes=USD", timeout=12)
        resp.raise_for_status()
        paprika_data = resp.json()
        formatted = []
        for item in paprika_data[:limit]:
            quotes = item.get("quotes", {}).get("USD", {})
            formatted.append({
                "id": item.get("id", ""),
                "symbol": item.get("symbol", "").lower(),
                "name": item.get("name", ""),
                "market_cap_rank": item.get("rank", 0),
                "market_cap": quotes.get("market_cap", 0),
                "current_price": quotes.get("price", 0),
                "price_change_percentage_24h": quotes.get("percent_change_24h", 0),
            })
        print(f"✅ CoinPaprika 備用源取得成功，載入 {len(formatted)} 檔幣種市值資訊")
        _save_cache(cache_file, formatted)
        return formatted
    except Exception as e:
        print(f"⚠️ CoinPaprika 備用源請求失敗: {e}")

    # 備用源 2: 基礎大幣靜態清單
    top_defaults = [
        ("BTC", "Bitcoin", 1), ("ETH", "Ethereum", 2), ("BNB", "BNB", 4),
        ("SOL", "Solana", 5), ("XRP", "XRP", 6), ("DOGE", "Dogecoin", 7),
        ("ADA", "Cardano", 8), ("AVAX", "Avalanche", 9), ("SUI", "Sui", 10),
        ("LINK", "Chainlink", 11), ("SHIB", "Shiba Inu", 12), ("TRX", "TRON", 13),
        ("DOT", "Polkadot", 14), ("NEAR", "NEAR Protocol", 15), ("APT", "Aptos", 16),
        ("UNI", "Uniswap", 17), ("LTC", "Litecoin", 18), ("PEPE", "Pepe", 19),
        ("ICP", "Internet Computer", 20), ("ETC", "Ethereum Classic", 21),
    ]
    return [
        {
            "id": sym.lower(), "symbol": sym.lower(), "name": name,
            "market_cap_rank": rank, "market_cap": 0,
            "current_price": 0, "price_change_percentage_24h": 0,
        }
        for sym, name, rank in top_defaults
    ]


def is_excluded_coin(item):
    """判斷代幣是否為穩定幣或包裝/質押代幣"""
    sym = (item.get("symbol") or "").lower()
    cid = (item.get("id") or "").lower()
    name = (item.get("name") or "").lower()

    if sym in EXCLUDED_SYMBOLS or cid in EXCLUDED_SYMBOLS:
        return True

    if any(k in sym for k in ["usd", "eur"]) and sym not in {"usd", "eur"}:
        return True
    if any(k in name for k in ["wrapped", "staked", "bridged"]):
        return True

    return False


def _fetch_ohlcv_paged(exchange, pair: str, timeframe: str, target_limit: int):
    """
    分頁抓取指定數量的 K 線（Bitget 永續合約單次查詢上限約 90~100 根）。
    若 target_limit <= 90 則直接單次查詢；若需要更多根數則向前分頁拼接。
    """
    if target_limit <= 90:
        return exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=target_limit)

    all_bars = []
    end_time = None
    max_pages = (target_limit // 80) + 2
    for _ in range(max_pages):
        params = {"endTime": end_time} if end_time else {}
        fetch_len = min(100, target_limit - len(all_bars))
        try:
            bars = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=fetch_len, params=params)
        except Exception:
            break
        if not bars:
            break
        if all_bars and bars[-1][0] >= all_bars[0][0]:
            bars = [b for b in bars if b[0] < all_bars[0][0]]
            if not bars:
                break
        all_bars = bars + all_bars
        if len(all_bars) >= target_limit or len(bars) < 50:
            break
        end_time = all_bars[0][0] - 1
        time.sleep(0.03)

    return all_bars[-target_limit:] if all_bars else []


def _fetch_daily_ohlcv_cached(exchange, pair: str, symbol: str, lookback: int):
    """
    抓取永續合約天圖日K（帶 24h 快取）。
    同一天（UTC）內直接從 cache 回傳，不重打 Bitget API。
    """
    today = _today_utc()
    cache_file = f"swap_1d_{symbol}_{today}.json"
    cached = _load_cache(cache_file)
    if cached:
        return cached  # list of [ts, o, h, l, c, v]

    ohlcv = _fetch_ohlcv_paged(exchange, pair, "1d", lookback)
    if ohlcv:
        _save_cache(cache_file, ohlcv)
    return ohlcv


def _fetch_ohlcv_slot_cached(
    exchange, pair: str, symbol: str, timeframe: str, interval_hours: int, limit: int
):
    """
    抓取永續合約指定時間框架的 K 線，按「實際收盤時段 slot」快取。
    一個 slot = interval_hours 小時。每當進入新 slot（新收盤），cache miss，重新抓取一次。
    即同一 slot 內多次 run 會直接命中，不重複呼叫 API。

    Args:
        interval_hours: K 棒間隔小時數（如 6 代表 6h K）
    """
    today = _today_utc()
    slot = _utc_slot(interval_hours)
    cache_file = f"swap_{timeframe}_{symbol}_{today}_slot{slot}.json"
    cached = _load_cache(cache_file)
    if cached:
        return cached

    ohlcv = _fetch_ohlcv_paged(exchange, pair, timeframe, limit)
    if ohlcv:
        _save_cache(cache_file, ohlcv)
    return ohlcv


def fetch_top_coins(top_n=TOP_N_COINS, lookback=LOOKBACK_BARS):
    """
    1. 從 CoinGecko 抓取市值排名，篩選前 top_n 個非穩定幣（帶日快取）
    2. 從 Bitget 抓取每個幣種的 USDT-M 永續合約：
       - 天圖日K：帶日快取 (24h key)，當天重用
       - 6h K：帶時段快取 (6h slot key)，每 6 小時更新一次
       - 4h K：帶時段快取 (4h slot key)，每 4 小時更新一次
       - 1h K：每次 fresh fetch（策略條件 2、4 需要即時 RSI，每小時都可能有新 bar）

    Returns:
        list[dict]: 每個幣的完整資訊與多時間框架 K 棒資料
    """
    exchange = get_exchange()
    print(f"📡 載入 {EXCHANGE_ID.capitalize()} 永續合約市場 (USDT-M Perpetual Futures)...")
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"❌ 載入 {EXCHANGE_ID} 合約市場失敗: {e}")
        return []

    # 取得 Bitget USDT-M 永續合約活躍交易對 (linear swap)
    swap_pairs = {
        s for s, m in markets.items()
        if m.get("swap") and m.get("linear") and m.get("active", True)
    }

    cg_data = fetch_coingecko_candidates(limit=100)
    if not cg_data:
        print("❌ 無法取得 CoinGecko 數據")
        return []

    selected_candidates = []
    for item in cg_data:
        if is_excluded_coin(item):
            continue

        symbol = item.get("symbol", "").upper()
        name = item.get("name", "")
        rank = item.get("market_cap_rank", 0)
        pair = f"{symbol}/USDT:USDT"  # CCXT USDT-M 永續合約標的
        display_pair = f"{symbol}/USDT"

        if pair not in swap_pairs:
            continue

        selected_candidates.append({
            "rank": rank,
            "symbol": symbol,
            "name": name,
            "pair": pair,
            "display_pair": display_pair,
            "market_cap": item.get("market_cap", 0),
            "price_cg": item.get("current_price", 0),
            "change_24h_cg": (item.get("price_change_percentage_24h") or 0) / 100.0,
            "trade_symbol": f"BITGET:{symbol}USDT.P",  # TradingView 永續合約代號 (帶 .P)
        })

        if len(selected_candidates) >= top_n:
            break

    print(f"✅ 已篩選出前 {len(selected_candidates)} 檔永續合約幣種，開始抓取合約 K 線資料...")

    coins = []
    for c in selected_candidates:
        pair = c["pair"]
        symbol = c["symbol"]
        try:
            # === 天圖日K（合約快取版，當天重用）===
            ohlcv = _fetch_daily_ohlcv_cached(exchange, pair, symbol, lookback)
            if not ohlcv or len(ohlcv) < 30:
                print(f"⚠️ {pair} K 線資料不足 (僅 {len(ohlcv) if ohlcv else 0} 根)，略過")
                continue

            completed_bars = ohlcv[:-1] if len(ohlcv) > 1 else ohlcv
            c["ohlcv"] = completed_bars
            latest_bar = completed_bars[-1]
            c["open"] = latest_bar[1]
            c["high"] = latest_bar[2]
            c["low"] = latest_bar[3]
            c["close"] = latest_bar[4]
            c["vol"] = latest_bar[5]
            c["vol_prev"] = completed_bars[-2][5] if len(completed_bars) >= 2 else c["vol"]
            c["vol_ma10"] = (
                sum(b[5] for b in completed_bars[-10:]) / 10.0
                if len(completed_bars) >= 10 else c["vol"]
            )

            # === 1h K（fresh fetch，RSI 計算用，含分頁確保 200 根）===
            try:
                ohlcv_1h = _fetch_ohlcv_paged(exchange, pair, "1h", LOOKBACK_BARS_1H)
                c["ohlcv_1h"] = ohlcv_1h[:-1] if ohlcv_1h and len(ohlcv_1h) > 1 else (ohlcv_1h or [])
            except Exception as e:
                print(f"  ⚠️ {pair} 1h K 線抓取失敗: {e}")
                c["ohlcv_1h"] = []

            time.sleep(0.05)

            # === 6h K（slot 快取，每 6 小時收盤更新一次）===
            try:
                ohlcv_6h = _fetch_ohlcv_slot_cached(
                    exchange, pair, symbol, "6h", 6, LOOKBACK_BARS_6H
                )
                c["ohlcv_6h"] = ohlcv_6h[:-1] if ohlcv_6h and len(ohlcv_6h) > 1 else (ohlcv_6h or [])
            except Exception as e:
                print(f"  ⚠️ {pair} 6h K 線抓取失敗: {e}")
                c["ohlcv_6h"] = []

            time.sleep(0.05)

            # === 4h K（slot 快取，每 4 小時收盤更新一次）===
            try:
                ohlcv_4h = _fetch_ohlcv_slot_cached(
                    exchange, pair, symbol, "4h", 4, LOOKBACK_BARS_4H
                )
                c["ohlcv_4h"] = ohlcv_4h[:-1] if ohlcv_4h and len(ohlcv_4h) > 1 else (ohlcv_4h or [])
            except Exception as e:
                print(f"  ⚠️ {pair} 4h K 線抓取失敗: {e}")
                c["ohlcv_4h"] = []

            coins.append(c)
        except Exception as e:
            print(f"⚠️ 抓取 {pair} K 線失敗: {e}")

        time.sleep(0.05)

    today = _today_utc()
    slot_6h = _utc_slot(6)
    slot_4h = _utc_slot(4)
    hit_1d = sum(1 for c in coins if _load_cache(f"swap_1d_{c['symbol']}_{today}.json") is not None)
    hit_6h = sum(1 for c in coins if _load_cache(f"swap_6h_{c['symbol']}_{today}_slot{slot_6h}.json") is not None)
    hit_4h = sum(1 for c in coins if _load_cache(f"swap_4h_{c['symbol']}_{today}_slot{slot_4h}.json") is not None)
    n = len(coins)
    print(
        f"🎉 成功完成 {n} 個永續合約幣種 K 線數據抓取！"
        f"（合約日K 快取命中: {hit_1d}/{n}，"
        f"6h slot{slot_6h} 命中: {hit_6h}/{n}，"
        f"4h slot{slot_4h} 命中: {hit_4h}/{n}，"
        f"1h fresh fetch）"
    )
    return coins


if __name__ == "__main__":
    top_coins = fetch_top_coins(5)
    for i, c in enumerate(top_coins, 1):
        print(f"{i}. [CG #{c['rank']}] {c['symbol']} ({c['name']}) — {c['pair']}")
        print(f"   收盤價: ${c['close']:,.2f}  市值: ${c['market_cap']/1e9:.2f}B")
        print(f"   日 K 數量: {len(c['ohlcv'])} 根")
        print(f"   VOL: {c['vol']:,.1f} | MA10: {c['vol_ma10']:,.1f} | >MA10: {'✅' if c['vol'] > c['vol_ma10'] else '❌'}")
        print()
