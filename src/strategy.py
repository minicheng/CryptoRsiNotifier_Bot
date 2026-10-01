"""
合約波段策略判斷模組
基於多時間框架的 5 大條件策略

策略五大條件：
  1. RD 趨勢判斷 (statusRD)  — Bitget 日K EMA10/EMA20 與 K 棒位置（持態機制：無中性 ⚪，持續維持 🟢 或 🔴）
     - 多方: 日 Low > EMA10 且 日 Low > EMA20
     - 空方: 日 High < EMA10 且 日 High < EMA20
     - 已過河拆橋天數、已掉入河中次數（與舊版相同）
  2. RSI 趨勢 (1小時K, RSI 14)
     - 多方進場: RSI < 30（超賣）
     - 空方進場: RSI > 70（超買）
  3. 平均K線趨勢 (6小時K, Heikin-Ashi)
     - NTZ: K 線同時有上影線和下影線（多空皆同條件）
  4. RSI 趨勢 (1小時K, RSI 14)
     - 多方: RSI < 50
     - 空方: RSI > 50
  5. OBV 趨勢 (天圖日K, OBV Oscillator = OBV - EMA(OBV, 21))
     - 多方條件1: OBV Oscillator > 0
     - 多方條件2: OBV Oscillator < 0 但 OBV 量縮（絕對值縮小）
     - 空方條件1: OBV Oscillator < 0
     - 空方條件2: OBV Oscillator > 0 但 OBV 量縮（絕對值縮小）

進出場訊號：
  - 合約做多進場: RD多 + RSI<30 + 平均K線已出現NTZ + RSI<50 + OBV條件(1或2)
  - 合約做多出場: RSI > 70
  - 合約做空進場: RD空 + RSI>70 + 平均K線已出現NTZ + RSI>50 + OBV條件(1或2)
  - 合約做空出場: RSI < 30
"""

import datetime

try:
    from config import RSI_PERIOD, OBV_EMA_PERIOD, MAX_SIGNAL_AGE_HOURS
except ImportError:
    RSI_PERIOD = 14
    OBV_EMA_PERIOD = 21
    MAX_SIGNAL_AGE_HOURS = 24


def calculate_ema(prices, period):
    """計算指數移動平均線 (EMA)"""
    if not prices or len(prices) == 0:
        return []
    ema = [prices[0]]
    multiplier = 2.0 / (period + 1.0)
    for price in prices[1:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def calculate_rsi_series(closes, period=14):
    """
    計算完整的 RSI 序列 (Wilder's smoothing method)

    Args:
        closes (list): 收盤價序列
        period (int): RSI 週期，預設 14

    Returns:
        list[float]: 與 closes 等長的 RSI 序列
    """
    if len(closes) < period + 1:
        return [50.0] * len(closes)

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0.0) for c in changes]
    losses = [abs(min(c, 0.0)) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_series = [50.0] * period
    if avg_loss == 0:
        rsi_series.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_series.append(100.0 - (100.0 / (1.0 + rs)))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_series.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_series.append(100.0 - (100.0 / (1.0 + rs)))

    return rsi_series


def calculate_rsi(closes, period=14):
    """
    計算最新 RSI (Relative Strength Index)
    """
    series = calculate_rsi_series(closes, period)
    return series[-1] if series else 50.0


def calculate_heikin_ashi(ohlcv):
    """
    計算 Heikin-Ashi K 線

    Args:
        ohlcv (list): 標準 OHLCV 資料 [[ts, o, h, l, c, v], ...]

    Returns:
        list[dict]: Heikin-Ashi K 線 [{"open", "high", "low", "close"}, ...]
    """
    if not ohlcv:
        return []

    ha_bars = []
    for i, bar in enumerate(ohlcv):
        o, h, l, c = bar[1], bar[2], bar[3], bar[4]
        ha_close = (o + h + l + c) / 4.0

        if i == 0:
            ha_open = (o + c) / 2.0
        else:
            ha_open = (ha_bars[i - 1]["open"] + ha_bars[i - 1]["close"]) / 2.0

        ha_high = max(h, ha_open, ha_close)
        ha_low = min(l, ha_open, ha_close)

        ha_bars.append({
            "open": ha_open,
            "high": ha_high,
            "low": ha_low,
            "close": ha_close,
        })

    return ha_bars


def is_ntz(ha_bar):
    """
    判斷 Heikin-Ashi K 線是否為 NTZ（同時有上影線和下影線）

    Args:
        ha_bar (dict): 含 open, high, low, close 的 Heikin-Ashi K 棒

    Returns:
        bool: True 表示 NTZ
    """
    body_top = max(ha_bar["open"], ha_bar["close"])
    body_bottom = min(ha_bar["open"], ha_bar["close"])
    has_upper_shadow = ha_bar["high"] > body_top
    has_lower_shadow = ha_bar["low"] < body_bottom
    return has_upper_shadow and has_lower_shadow


def calculate_obv(ohlcv):
    """
    計算標準 OBV (On-Balance Volume)

    Args:
        ohlcv (list): OHLCV 資料

    Returns:
        list[float]: OBV 序列
    """
    if not ohlcv:
        return []

    obv = [0.0]
    for i in range(1, len(ohlcv)):
        c = ohlcv[i][4]      # close
        c_prev = ohlcv[i - 1][4]
        v = ohlcv[i][5]      # volume

        if c > c_prev:
            obv.append(obv[-1] + v)
        elif c < c_prev:
            obv.append(obv[-1] - v)
        else:
            obv.append(obv[-1])

    return obv


def calculate_obv_oscillator_series(ohlcv, ema_period=21):
    """
    計算完整的 OBV Oscillator 序列 = OBV - EMA(OBV, ema_period)

    Args:
        ohlcv (list): 4小時K OHLCV 資料
        ema_period (int): EMA 週期，預設 21

    Returns:
        list[float]: 與 ohlcv 等長的 OBV Oscillator 序列
    """
    if not ohlcv:
        return []
    obv = calculate_obv(ohlcv)
    if len(obv) < ema_period + 1:
        return [0.0] * len(ohlcv)

    obv_ema = calculate_ema(obv, ema_period)
    osc = [o - e for o, e in zip(obv, obv_ema)]
    return osc


def calculate_obv_oscillator(ohlcv, ema_period=21):
    """
    計算最新和前一根的 OBV Oscillator 值
    """
    osc = calculate_obv_oscillator_series(ohlcv, ema_period)
    if not osc:
        return 0.0, 0.0
    return osc[-1], osc[-2] if len(osc) >= 2 else (osc[-1], 0.0)


def analyze_coin(coin):
    """
    分析單一幣種，計算完整技術指標、RD 歷史天數與掉河次數、進出場訊號。

    Args:
        coin (dict): 包含 ohlcv (日K)、ohlcv_1h、ohlcv_6h、ohlcv_4h 的字典

    Returns:
        dict: 策略分析結果
    """
    ohlcv = coin.get("ohlcv", [])
    symbol = coin.get("symbol", "")
    if not ohlcv or len(ohlcv) < 30:
        raise ValueError(f"K 線資料不足: {len(ohlcv)} 根")

    closes = [b[4] for b in ohlcv]
    opens = [b[1] for b in ohlcv]
    highs = [b[2] for b in ohlcv]
    lows = [b[3] for b in ohlcv]
    vols = [b[5] for b in ohlcv]
    n_bars = len(ohlcv)

    # 技術指標計算 (日K)
    ema10_series = calculate_ema(closes, 10)
    ema20_series = calculate_ema(closes, 20)

    # 最新完成日 K 數值
    close = closes[-1]
    open_price = opens[-1]
    high = highs[-1]
    low = lows[-1]
    ema10 = ema10_series[-1]
    ema20 = ema20_series[-1]

    # 24h 漲跌幅（以最新完成日 K 計算）
    prev_close = closes[-2] if n_bars >= 2 else close
    change = (close - prev_close) / prev_close if prev_close > 0 else 0.0

    # ===== 1. RD 趨勢持態機制 (State Machine) =====
    # 規則：
    # - is_up: low > ema10 且 low > ema20
    # - is_down: high < ema10 且 high < ema20
    # 一但確認為 🟢 (多頭) 後持續維持，直到轉型為 🔴 (空頭)；反之亦然。無中性 (⚪)。
    state = 0  # 3 = 🟢 多頭, -3 = 🔴 空頭
    flip_idx = 0

    for i in range(n_bars):
        is_up = (lows[i] > ema10_series[i] and lows[i] > ema20_series[i])
        is_down = (highs[i] < ema10_series[i] and highs[i] < ema20_series[i])

        old_state = state
        if is_up:
            state = 3
        elif is_down:
            state = -3

        # 紀錄最新一次翻轉的時間點
        if old_state != state and state != 0:
            flip_idx = i

    # 若歷史中從未明確翻轉過，預設以第 0 根開始
    status_rd = state if state != 0 else (3 if close >= ema10 else -3)

    # 已過河拆橋天數：從翻轉日到最新完成日 K 的天數（當天穿越即為第 1 天）
    trend_days = n_bars - flip_idx

    flip_timestamp = ohlcv[flip_idx][0]
    flip_date = datetime.datetime.fromtimestamp(
        flip_timestamp / 1000, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%d")

    # 最新完成日 K 棒的日期
    latest_bar_date = datetime.datetime.fromtimestamp(
        ohlcv[-1][0] / 1000, tz=datetime.timezone.utc
    ).strftime("%m/%d")
    latest_bar_date_full = datetime.datetime.fromtimestamp(
        ohlcv[-1][0] / 1000, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%d")

    # ===== 已掉入河中次數計算（含日期標註 — 即時觸發制） =====
    # 🟢 多頭：從回看歷史找到最近一次明確穿越後，當 K 棒（必須是陰 K）滿足以下條件之一：
    #          1. 收盤價夾在兩條 EMA 中間 (EMA_min <= close <= EMA_max)
    #          2. 收盤價 < EMA10 且 < EMA20 (close < EMA_min)
    #          3. 最低價跌入或貫穿兩條 EMA (low <= EMA_max，包含夾在中間與插針跌破河底)
    #          一掉入河中立即計入次數並記錄日期；在重回河面 (low > EMA_max) 前不重複累加。
    # 🔴 空頭：從回看歷史找到最近一次明確穿越後，當 K 棒（必須是陽 K）滿足以下條件之一：
    #          1. 收盤價夾在兩條 EMA 中間 (EMA_min <= close <= EMA_max)
    #          2. 收盤價 > EMA10 且 > EMA20 (close > EMA_max)
    #          3. 最高價升入或貫穿兩條 EMA (high >= EMA_min，包含夾在中間與插針突破河頂)
    #          一掉入河中立即計入次數並記錄日期；在重回河面 (high < EMA_min) 前不重複累加。
    dips_completed = 0
    dip_dates = []
    in_dip = False

    chinese_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五"]

    if status_rd == 3:  # 多頭
        for i in range(flip_idx, n_bars):
            e_min = min(ema10_series[i], ema20_series[i])
            e_max = max(ema10_series[i], ema20_series[i])
            is_above = (lows[i] > e_max)

            # 陰 K 且滿足條件之一（收盤掉入、收盤跌破、或最低價跌入/貫穿河面）:
            cond1 = (e_min <= closes[i] <= e_max)      # 收盤價夾在兩條 EMA 中間
            cond2 = (closes[i] < e_min)                # 收盤價 < EMA10 且 < EMA20
            cond3 = (lows[i] <= e_max)                 # 最低價跌入或貫穿兩條 EMA (含夾在中間與插針跌破河底)
            is_dip_bar = (closes[i] < opens[i]) and (cond1 or cond2 or cond3)

            dt_str = datetime.datetime.fromtimestamp(
                ohlcv[i][0] / 1000, tz=datetime.timezone.utc
            ).strftime("%m/%d")

            if not in_dip:
                if is_dip_bar:
                    in_dip = True
                    dips_completed += 1
                    dip_dates.append(dt_str)
            else:
                if is_above:
                    in_dip = False

    elif status_rd == -3:  # 空頭
        for i in range(flip_idx, n_bars):
            e_min = min(ema10_series[i], ema20_series[i])
            e_max = max(ema10_series[i], ema20_series[i])
            is_below = (highs[i] < e_min)

            # 陽 K 且滿足條件之一（收盤升入、收盤突破、或最高價升入/貫穿河面）:
            cond1 = (e_min <= closes[i] <= e_max)      # 收盤價夾在兩條 EMA 中間
            cond2 = (closes[i] > e_max)                # 收盤價 > EMA10 且 > EMA20
            cond3 = (highs[i] >= e_min)                # 最高價升入或貫穿兩條 EMA (含夾在中間與插針突破河頂)
            is_dip_bar = (closes[i] >= opens[i]) and (cond1 or cond2 or cond3)

            dt_str = datetime.datetime.fromtimestamp(
                ohlcv[i][0] / 1000, tz=datetime.timezone.utc
            ).strftime("%m/%d")

            if not in_dip:
                if is_dip_bar:
                    in_dip = True
                    dips_completed += 1
                    dip_dates.append(dt_str)
            else:
                if is_below:
                    in_dip = False

    # 格式化日期標註字串，例如：3 次（掉入第一次(07/28)、掉入第二次(08/11)、掉入第三次(09/02)）
    if len(dip_dates) > 0:
        dates_detail = "、".join(
            f"掉入第{chinese_nums[k] if k < len(chinese_nums) else str(k+1)}次({d})"
            for k, d in enumerate(dip_dates)
        )
        dips_str = f"{len(dip_dates)} 次（{dates_detail}）"
    else:
        dips_str = "0 次"

    # 注意事項：掉河次數 >= 2
    has_warning = (dips_completed >= 2)

    # ===== 1. RD 趨勢 (天圖確認) =====
    cond1_ok = (status_rd == 3) if status_rd == 3 else (status_rd == -3)

    # ===== 2. RSI 條件 2 (1h K 超賣/超買發生點，發生於 RD 趨勢確立後) =====
    ohlcv_1h = coin.get("ohlcv_1h", [])
    closes_1h = [b[4] for b in ohlcv_1h] if ohlcv_1h else []
    rsi_series = calculate_rsi_series(closes_1h, RSI_PERIOD)
    rsi_value = rsi_series[-1] if rsi_series else 50.0

    tw_tz = datetime.timezone(datetime.timedelta(hours=8))

    # 回溯尋找在近期（近 72 根 1h K 線內，且在 RD 趨勢確立後）的超賣/超買觸發點
    # ★ 正向搜尋：找「最早的」RSI<30 / RSI>70 觸發棒，因為後續步驟必須接續在此之後
    lookback_1h = min(72, len(rsi_series)) if rsi_series else 0
    cond2_ok = False
    cond2_idx = None
    cond2_ts = None
    cond2_open_ts = None
    cond2_time = None
    cond2_val = None

    search_start_1h = max(0, len(rsi_series) - lookback_1h)
    if status_rd == 3:  # 做多：尋找最早的 RSI < 30 K 棒
        for i in range(search_start_1h, len(rsi_series)):
            bar_ts = ohlcv_1h[i][0]
            if bar_ts < flip_timestamp:
                continue
            if rsi_series[i] < 30:
                cond2_ok = True
                cond2_idx = i
                cond2_ts = bar_ts + 3600 * 1000  # 該 1h K 收盤時間戳
                cond2_open_ts = bar_ts
                cond2_val = rsi_series[i]
                cond2_time = datetime.datetime.fromtimestamp(bar_ts / 1000, tz=tw_tz).strftime("%m/%d %H:%M")
                break
    else:  # 做空：尋找最早的 RSI > 70 K 棒
        for i in range(search_start_1h, len(rsi_series)):
            bar_ts = ohlcv_1h[i][0]
            if bar_ts < flip_timestamp:
                continue
            if rsi_series[i] > 70:
                cond2_ok = True
                cond2_idx = i
                cond2_ts = bar_ts + 3600 * 1000
                cond2_open_ts = bar_ts
                cond2_val = rsi_series[i]
                cond2_time = datetime.datetime.fromtimestamp(bar_ts / 1000, tz=tw_tz).strftime("%m/%d %H:%M")
                break

    # ===== 3. 平均K線 NTZ 轉折 (6h Heikin-Ashi) =====
    # 時序前置限制：必須在條件 2 發生之後或當下 (T3 >= T2)！
    # ★ 正向搜尋：找「最早的」符合時序的 NTZ 轉折棒
    ohlcv_6h = coin.get("ohlcv_6h", [])
    ha_bars = calculate_heikin_ashi(ohlcv_6h)
    cond3_ok = False
    cond3_idx = None
    cond3_ts = None
    cond3_time = None

    if cond2_ok and cond2_ts and ha_bars:
        for i in range(len(ha_bars)):
            bar_start_ts = ohlcv_6h[i][0]
            bar_end_ts = bar_start_ts + 6 * 3600 * 1000
            # 關鍵時序約束：該 6h NTZ K 棒的收盤時間必須 >= 條件 2 的觸發時間
            if bar_end_ts >= cond2_ts and is_ntz(ha_bars[i]):
                cond3_ok = True
                cond3_idx = i
                cond3_ts = bar_end_ts
                t_start_str = datetime.datetime.fromtimestamp(bar_start_ts / 1000, tz=tw_tz).strftime("%m/%d %H:%M")
                t_end_str = datetime.datetime.fromtimestamp(bar_end_ts / 1000, tz=tw_tz).strftime("%H:%M")
                cond3_time = f"{t_start_str}~{t_end_str}"
                break

    # ===== 4. RSI 方向確認 (1h K 方向與中軸判定) =====
    # 時序前置限制：必須在條件 3 (NTZ 轉折) 出現之後確認 (T4 >= T3)！
    # ★ 正向搜尋：找 NTZ 收盤後「最早的」RSI<50 / RSI>50 的 1h K 棒
    cond4_ok = False
    cond4_idx = None
    cond4_ts = None
    cond4_end_ts = None
    cond4_time = None
    cond4_val = None

    if cond3_ok and cond3_ts:
        for i in range(len(ohlcv_1h)):
            bar_ts = ohlcv_1h[i][0]
            bar_end_ts_i = bar_ts + 3600 * 1000
            if bar_end_ts_i < cond3_ts:
                continue
            rsi_i = rsi_series[i] if i < len(rsi_series) else 50.0
            if status_rd == 3:
                if rsi_i < 50:
                    cond4_ok = True
                    cond4_idx = i
                    cond4_ts = bar_ts
                    cond4_end_ts = bar_end_ts_i
                    cond4_val = rsi_i
                    cond4_time = datetime.datetime.fromtimestamp(bar_ts / 1000, tz=tw_tz).strftime("%m/%d %H:%M")
                    break
            else:
                if rsi_i > 50:
                    cond4_ok = True
                    cond4_idx = i
                    cond4_ts = bar_ts
                    cond4_end_ts = bar_end_ts_i
                    cond4_val = rsi_i
                    cond4_time = datetime.datetime.fromtimestamp(bar_ts / 1000, tz=tw_tz).strftime("%m/%d %H:%M")
                    break

    # ===== 5. OBV Oscillator 動能確認 (天圖日K) =====
    # 時序前置限制：接續步驟 4 (1h RSI<50/RSI>50) 之時間點，確認當時的天圖 OBV 動能！
    obv_osc_series = calculate_obv_oscillator_series(ohlcv, OBV_EMA_PERIOD)  # 使用日K

    cond5_idx = None
    if cond4_ok and cond4_ts:
        # 尋找涵蓋步驟 4 時間點的該根天圖日 K
        for i, bar in enumerate(ohlcv):
            bar_start = bar[0]
            bar_end = bar_start + 86400 * 1000
            if bar_start <= cond4_ts < bar_end:
                cond5_idx = i
                break
        if cond5_idx is None:
            cond5_idx = len(ohlcv) - 1
    else:
        cond5_idx = len(ohlcv) - 1 if ohlcv else None

    if cond5_idx is not None and cond5_idx < len(obv_osc_series):
        curr_osc = obv_osc_series[cond5_idx]
        prev_osc = obv_osc_series[cond5_idx - 1] if cond5_idx > 0 else 0.0
        cond5_ts = ohlcv[cond5_idx][0]
        cond5_time = datetime.datetime.fromtimestamp(cond5_ts / 1000, tz=tw_tz).strftime("%m/%d")
    else:
        curr_osc = obv_osc_series[-1] if obv_osc_series else 0.0
        prev_osc = obv_osc_series[-2] if len(obv_osc_series) >= 2 else 0.0
        cond5_ts = ohlcv[-1][0] if ohlcv else 0
        cond5_time = datetime.datetime.fromtimestamp(cond5_ts / 1000, tz=tw_tz).strftime("%m/%d") if cond5_ts else ""

    is_shrinking = abs(curr_osc) < abs(prev_osc)

    cond5_ok = False
    if cond4_ok:
        if status_rd == 3:
            cond5_ok = (curr_osc > 0) or (curr_osc < 0 and is_shrinking)
        else:
            cond5_ok = (curr_osc < 0) or (curr_osc > 0 and is_shrinking)

    # ===== 進出場訊號判定 =====
    long_entry_all_met = (status_rd == 3 and cond1_ok and cond2_ok and cond3_ok and cond4_ok and cond5_ok)
    short_entry_all_met = (status_rd == -3 and cond1_ok and cond2_ok and cond3_ok and cond4_ok and cond5_ok)

    # 計算訊號時效（年齡）
    now_ts = ohlcv_1h[-1][0] if ohlcv_1h else (ohlcv[-1][0] if ohlcv else 0)
    signal_age_hours = 0.0
    if cond4_ts and now_ts:
        signal_age_hours = max(0.0, (now_ts - cond4_ts) / 3600000.0)

    # 僅在時效內（例如 24 小時內）才算「當前新進場訊號」，超過則為「波段持倉中」
    is_fresh_entry = (signal_age_hours <= MAX_SIGNAL_AGE_HOURS)
    long_entry = long_entry_all_met and is_fresh_entry
    short_entry = short_entry_all_met and is_fresh_entry
    in_position = (long_entry_all_met or short_entry_all_met) and not is_fresh_entry

    # 建立進場唯一 ID (signal_key)
    entry_signal_key = ""
    if long_entry_all_met and cond4_ts:
        entry_signal_key = f"{symbol}_long_entry_{cond4_ts}"
    elif short_entry_all_met and cond4_ts:
        entry_signal_key = f"{symbol}_short_entry_{cond4_ts}"

    # 出場判定與唯一 ID
    long_exit = (status_rd == 3 and rsi_value > 70)
    short_exit = (status_rd == -3 and rsi_value < 30)

    exit_signal_key = ""
    if long_exit and rsi_series and ohlcv_1h:
        # 回溯找到連續 >70 的第一根 K 棒時間，確保整段超買期間 signal_key 不變
        idx = len(rsi_series) - 1
        while idx > 0 and rsi_series[idx - 1] > 70:
            idx -= 1
        exit_cross_ts = ohlcv_1h[idx][0] if idx < len(ohlcv_1h) else now_ts
        exit_signal_key = f"{symbol}_long_exit_{exit_cross_ts}"
    elif short_exit and rsi_series and ohlcv_1h:
        idx = len(rsi_series) - 1
        while idx > 0 and rsi_series[idx - 1] < 30:
            idx -= 1
        exit_cross_ts = ohlcv_1h[idx][0] if idx < len(ohlcv_1h) else now_ts
        exit_signal_key = f"{symbol}_short_exit_{exit_cross_ts}"

    active_signal_key = entry_signal_key if (long_entry or short_entry) else (exit_signal_key if (long_exit or short_exit) else "")

    # ===== 5 步時序檢核清單 =====
    c1_txt = f"(1) 步驟1 天圖RD趨勢 ({'多頭向上' if status_rd==3 else '空頭向下'}, {trend_days}天) {'✅' if cond1_ok else '❌'}"
    if status_rd == 3:
        c2_txt = f"(2) 步驟2 1h RSI<30 超賣 ({cond2_time} RSI={cond2_val:.1f}) {'✅' if cond2_ok else '❌'}" if cond2_time else f"(2) 步驟2 1h RSI<30 超賣 (未達超賣) ❌"
        c3_txt = f"(3) 步驟3 6h NTZ轉折 ({cond3_time}) {'✅' if cond3_ok else '❌'}" if cond3_time else f"(3) 步驟3 6h NTZ轉折 (無接續轉折) ❌"
        c4_val_str = f" RSI={cond4_val:.1f}" if cond4_val is not None else ""
        c4_txt = f"(4) 步驟4 1h RSI<50 蓄勢 ({cond4_time}{c4_val_str}) {'✅' if cond4_ok else '❌'}" if cond4_time else f"(4) 步驟4 1h RSI<50 蓄勢 (未確認) ❌"
        obv_det = "OBV>0" if curr_osc > 0 else ("OBV量縮" if is_shrinking else f"OBV={curr_osc:.0f}")
        c5_txt = f"(5) 步驟5 天圖OBV動能 ({cond5_time} {obv_det}) {'✅' if cond5_ok else '❌'}"
    else:
        c2_txt = f"(2) 步驟2 1h RSI>70 超買 ({cond2_time} RSI={cond2_val:.1f}) {'✅' if cond2_ok else '❌'}" if cond2_time else f"(2) 步驟2 1h RSI>70 超買 (未達超買) ❌"
        c3_txt = f"(3) 步驟3 6h NTZ轉折 ({cond3_time}) {'✅' if cond3_ok else '❌'}" if cond3_time else f"(3) 步驟3 6h NTZ轉折 (無接續轉折) ❌"
        c4_val_str = f" RSI={cond4_val:.1f}" if cond4_val is not None else ""
        c4_txt = f"(4) 步驟4 1h RSI>50 弱勢 ({cond4_time}{c4_val_str}) {'✅' if cond4_ok else '❌'}" if cond4_time else f"(4) 步驟4 1h RSI>50 弱勢 (未確認) ❌"
        obv_det = "OBV<0" if curr_osc < 0 else ("OBV量縮" if is_shrinking else f"OBV={curr_osc:.0f}")
        c5_txt = f"(5) 步驟5 天圖OBV動能 ({cond5_time} {obv_det}) {'✅' if cond5_ok else '❌'}"

    checklist = [c1_txt, c2_txt, c3_txt, c4_txt, c5_txt]
    conditions_met_count = sum([1 for ok in [cond1_ok, cond2_ok, cond3_ok, cond4_ok, cond5_ok] if ok])

    # ===== 操作建議與注意事項自動生成（專為 5 步時序波段策略設計） =====
    if status_rd == 3:  # 多頭
        if long_entry:
            action_advice = "滿足 5 步驟嚴格時序共振！天圖多頭順勢 + 1h RSI超賣打底 + 6h NTZ轉折確立 + 1h RSI中軸蓄勢 + 天圖OBV買盤充沛，觸發「合約做多進場訊號」，可順勢建立多單。"
            caution_note = "進場後請依策略監控 1h RSI，當 1h RSI 衝入超買區 (>70) 時為多單出場訊號；可設防守止損於步驟3 NTZ 轉折低點。"
        elif in_position:
            action_advice = f"已於 {cond4_time} 滿足 5 步驟嚴格時序進場，目前處於波段多單持倉狀態（已持倉約 {int(signal_age_hours)} 小時）。"
            caution_note = "多單持倉中，請依策略持續監控 1h RSI 是否衝入 >70 獲利出場區。"
        elif long_exit:
            action_advice = "即時 1h RSI 已突破 70 進入極度超買區，短線多頭拉升力道耗盡，觸發「合約做多出場訊號」！"
            caution_note = "建議分批止盈或全部平倉獲利了結多單，鎖定波段利潤，切勿追高。"
        else:
            action_advice = f"天圖趨勢為多頭向上，目前已依序完成 {conditions_met_count}/5 個時序條件，建議觀望等待條件全數共振。"
            if conditions_met_count == 4:
                caution_note = "前4步皆已達成，僅待天圖OBV確認（OBV>0 或 量縮收窄），切勿提前搶跑進場。"
            elif conditions_met_count >= 1:
                caution_note = "多頭格局延續中，尚未完成完整共振時序，建議保持觀望耐心等待。"
            else:
                caution_note = "均線多頭排列良好，目前尚未出現拉回打底轉折訊號。"
    else:  # 空頭
        if short_entry:
            action_advice = "滿足 5 步驟嚴格時序共振！天圖空頭主趨勢 + 1h RSI超買反彈結束 + 6h NTZ轉折確立 + 1h RSI中軸下行 + 天圖OBV賣盤壓制，觸發「合約做空進場訊號」，可順勢建立空單。"
            caution_note = "進場後請依策略監控 1h RSI，當 1h RSI 跌入超賣區 (<30) 時為空單出場訊號；可設防守止損於步驟3 NTZ 轉折高點。"
        elif in_position:
            action_advice = f"已於 {cond4_time} 滿足 5 步驟嚴格時序進場，目前處於波段空單持倉狀態（已持倉約 {int(signal_age_hours)} 小時）。"
            caution_note = "空單持倉中，請依策略持續監控 1h RSI 是否跌入 <30 獲利出場區。"
        elif short_exit:
            action_advice = "即時 1h RSI 已跌破 30 進入極度超賣區，短線空頭下殺力道耗盡，觸發「合約做空出場訊號」！"
            caution_note = "建議分批止盈或全部平倉空單，提防超跌強烈反彈。"
        else:
            action_advice = f"天圖趨勢為空頭向下，目前已依序完成 {conditions_met_count}/5 個時序條件，建議觀望等待條件全數共振。"
            if conditions_met_count == 4:
                caution_note = "前4步皆已達成，僅待天圖OBV確認（OBV<0 或 量縮收窄），切勿提前搶跑進場。"
            elif conditions_met_count >= 1:
                caution_note = "空頭格局延續中，尚未完成完整共振時序，建議保持觀望耐心等待。"
            else:
                caution_note = "均線空頭排列，目前尚未出現反彈衝頂轉折訊號。"

    return {
        "symbol": coin.get("symbol", ""),
        "name": coin.get("name", ""),
        "pair": coin.get("pair", ""),
        "trade_symbol": coin.get("trade_symbol", ""),
        "rank": coin.get("rank", 0),
        "market_cap": coin.get("market_cap", 0),
        "close": close,
        "open": open_price,
        "high": high,
        "low": low,
        "change": change,
        "ema10": ema10,
        "ema20": ema20,
        "vol": vols[-1],
        # RD 歷史指標
        "status_rd": status_rd,
        "trend_days": trend_days,
        "flip_date": flip_date,
        "dips_completed": dips_completed,
        "dip_dates": dip_dates,
        "dips_str": dips_str,
        "in_dip": in_dip,
        "has_warning": has_warning,
        "latest_bar_date": latest_bar_date,
        "latest_bar_date_full": latest_bar_date_full,
        # 各時間框架資料序列
        "ohlcv": ohlcv,
        "ohlcv_1h": ohlcv_1h,
        "ohlcv_6h": ohlcv_6h,
        "ohlcv_4h": coin.get("ohlcv_4h", []),  # 保留向下相容，但 OBV 已改用天圖
        "ema10_series": ema10_series,
        "ema20_series": ema20_series,
        # RSI 條件細節 (條件2 & 條件4)
        "rsi": rsi_value,
        "rsi_series": rsi_series,
        "cond1_ok": cond1_ok,
        "cond2_ok": cond2_ok,
        "cond2_idx": cond2_idx,
        "cond2_ts": cond2_ts,
        "cond2_open_ts": cond2_open_ts,
        "cond2_time": cond2_time,
        "cond2_val": cond2_val,
        "cond3_ok": cond3_ok,
        "cond3_idx": cond3_idx,
        "cond3_ts": cond3_ts,
        "cond3_time": cond3_time,
        "cond4_ok": cond4_ok,
        "cond4_idx": cond4_idx,
        "cond4_ts": cond4_ts,
        "cond4_end_ts": cond4_end_ts,
        "cond4_time": cond4_time if cond4_time else "",
        "cond4_val": cond4_val if cond4_val is not None else rsi_value,
        # Heikin-Ashi NTZ (條件3 - 向下相容)
        "ha_bars": ha_bars,
        "ntz_appeared": cond3_ok,
        "ntz_bar_idx": cond3_idx,
        "ntz_time": cond3_time,
        # OBV Oscillator (條件5)
        "cond5_ok": cond5_ok,
        "cond5_idx": cond5_idx,
        "cond5_ts": cond5_ts,
        "cond5_time": cond5_time,
        "obv_osc_series": obv_osc_series,
        "obv_osc": curr_osc,
        "obv_osc_prev": prev_osc,
        "obv_is_shrinking": is_shrinking,
        "obv_long_ok": (curr_osc > 0) or (curr_osc < 0 and is_shrinking),
        "obv_short_ok": (curr_osc < 0) or (curr_osc > 0 and is_shrinking),
        # 進出場訊號與持倉狀態
        "long_entry": long_entry,
        "long_exit": long_exit,
        "short_entry": short_entry,
        "short_exit": short_exit,
        "in_position": in_position,
        "signal_key": active_signal_key,
        "entry_signal_key": entry_signal_key,
        "exit_signal_key": exit_signal_key,
        "signal_age_hours": signal_age_hours,
        "is_fresh_entry": is_fresh_entry,
        # 個幣卡片擴充欄位
        "checklist": checklist,
        "conditions_met_count": conditions_met_count,
        "action_advice": action_advice,
        "caution_note": caution_note,
    }


def analyze_all(coins):
    """
    分析所有幣種，回傳分析結果列表。

    Args:
        coins (list[dict]): scanner 取得的幣種列表

    Returns:
        list[dict]: 每個幣的分析結果
    """
    results = []
    for coin in coins:
        try:
            result = analyze_coin(coin)
            results.append(result)
        except (KeyError, TypeError, ValueError) as e:
            print(f"⚠️ 分析 {coin.get('symbol', '???')} 時出錯: {e}")
    return results


def get_signals(results):
    """
    從分析結果中提取有訊號的幣種。

    Args:
        results (list[dict]): analyze_all 的回傳值

    Returns:
        dict: 按訊號類型分類的結果
    """
    signals = {
        "long_entry": [],
        "long_exit": [],
        "short_entry": [],
        "short_exit": [],
    }

    for r in results:
        if r["long_entry"]:
            signals["long_entry"].append(r)
        if r["long_exit"]:
            signals["long_exit"].append(r)
        if r["short_entry"]:
            signals["short_entry"].append(r)
        if r["short_exit"]:
            signals["short_exit"].append(r)

    return signals


if __name__ == "__main__":
    from scanner import fetch_top_coins

    coins = fetch_top_coins(5)
    results = analyze_all(coins)

    print("=" * 65)
    print("合約波段策略分析結果（CoinGecko + Bitget CCXT）")
    print("=" * 65)

    for r in results:
        rd_color = "🟢" if r["status_rd"] == 3 else "🔴"
        ntz_str = "✅ NTZ" if r["ntz_appeared"] else "❌ 無NTZ"
        warn_str = " ⚠️【注意：已掉入河中 2 次以上】" if r["has_warning"] else ""

        print(f"\n{r['symbol']} ({r['name']}) — {r['pair']}")
        print(f"  💰 價格: ${r['close']:,.2f}  漲跌: {r['change']*100:+.2f}%")
        print(f"  RD趨勢: {rd_color}  |  已過河拆橋天數: {r['trend_days']} 天 (翻轉日: {r['flip_date']})")
        print(f"  已掉入河中次數: {r['dips_completed']} 次{warn_str}")
        print(f"  RSI(1h): {r['rsi']:.1f}  |  NTZ(6h): {ntz_str}")
        print(f"  OBV Oscillator(4h): {r['obv_osc']:.2f}  (量縮: {'是' if r['obv_is_shrinking'] else '否'})")

        if r["long_entry"]:
            print(f"  🚀 >>> 合約做多進場 <<<")
        if r["long_exit"]:
            print(f"  🛑 >>> 合約做多出場 <<<")
        if r["short_entry"]:
            print(f"  📉 >>> 合約做空進場 <<<")
        if r["short_exit"]:
            print(f"  🔄 >>> 合約做空出場 <<<")
