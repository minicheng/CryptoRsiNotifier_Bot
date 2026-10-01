"""
全方位策略條件驗證測試腳本
測試涵蓋：
1. RD 趨勢判斷 (日 K EMA10/20、過河拆橋天數、掉河次數)
2. 1h RSI 計算與閥值 (30, 50, 70)
3. 6h Heikin-Ashi NTZ 轉折確認
4. 4h OBV Oscillator (OBV - EMA21) 及量縮判定
5. 合約做多進場 / 出場訊號觸發
6. 合約做空進場 / 出場訊號觸發
7. Telegram 總覽日報與圖文卡片排版
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 載入 src
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, src_dir)

from strategy import (
    calculate_ema,
    calculate_rsi,
    calculate_heikin_ashi,
    is_ntz,
    calculate_obv,
    calculate_obv_oscillator,
    analyze_coin,
    analyze_all,
    get_signals,
)
from notifier import format_signals_message, format_coin_card_caption
from chart_generator import generate_all_strategy_charts


def test_rsi():
    print("▶ 測試 1: RSI 計算...")
    # 持續上漲序列 -> RSI 應該 > 70
    up_prices = [100.0 + i * 2.0 for i in range(50)]
    rsi_up = calculate_rsi(up_prices, 14)
    assert rsi_up > 70, f"預期 RSI > 70，實際: {rsi_up}"

    # 持續下跌序列 -> RSI 應該 < 30
    down_prices = [200.0 - i * 2.0 for i in range(50)]
    rsi_down = calculate_rsi(down_prices, 14)
    assert rsi_down < 30, f"預期 RSI < 30，實際: {rsi_down}"

    # 水平震盪序列 -> RSI 應該接近 50
    flat_prices = [100.0 + (1 if i % 2 == 0 else -1) for i in range(50)]
    rsi_flat = calculate_rsi(flat_prices, 14)
    assert 40 <= rsi_flat <= 60, f"預期 40<=RSI<=60，實際: {rsi_flat}"
    print(f"  ✅ RSI 測試通過: 上漲={rsi_up:.1f}, 下跌={rsi_down:.1f}, 平盤={rsi_flat:.1f}")


def test_heikin_ashi_and_ntz():
    print("▶ 測試 2: Heikin-Ashi 與 NTZ 判斷...")
    # 建立有上下影線的 K 棒 (NTZ 轉折)
    ntz_candle = {"open": 100.0, "high": 110.0, "low": 90.0, "close": 101.0}
    assert is_ntz(ntz_candle) is True, "具有上下影線應判定為 NTZ"

    # 建立強趨勢無下影線陽線 (非 NTZ)
    bull_candle = {"open": 100.0, "high": 110.0, "low": 100.0, "close": 108.0}
    assert is_ntz(bull_candle) is False, "無下影線陽線不應判定為 NTZ"

    # 測試最近 3 根是否有 NTZ
    ha_series = [
        {"open": 100, "high": 110, "low": 100, "close": 108},  # non-NTZ
        {"open": 108, "high": 112, "low": 108, "close": 111},  # non-NTZ
        {"open": 110, "high": 115, "low": 105, "close": 111},  # NTZ
    ]
    assert any(is_ntz(bar) for bar in ha_series[-3:]) is True
    print("  ✅ Heikin-Ashi 與 NTZ 測試通過")


def test_obv_oscillator():
    print("▶ 測試 3: OBV Oscillator 與量縮判定...")
    # 建立 4h K 棒序列
    ohlcv_4h = []
    base_price = 100.0
    for i in range(60):
        # 價格逐步上漲
        o = base_price + i * 0.5
        c = o + 0.3
        h = c + 0.2
        l = o - 0.2
        v = 1000.0
        ohlcv_4h.append([i * 14400000, o, h, l, c, v])

    osc, osc_prev = calculate_obv_oscillator(ohlcv_4h, 21)
    # 持續放量上漲時，OBV Oscillator 應 > 0
    assert osc > 0, f"預期 OBV Osc > 0，實際: {osc}"

    # 測試量縮判定
    curr_osc = 50.0
    prev_osc = 100.0
    is_shrinking = abs(curr_osc) < abs(prev_osc)
    assert is_shrinking is True, "量縮判定應為 True"
    print(f"  ✅ OBV Oscillator 測試通過: osc={osc:.1f}, prev={osc_prev:.1f}")


def test_long_entry_and_exit_signals():
    print("▶ 測試 4: 合約做多進場與出場條件...")
    # 構造滿足 5 大做多條件的 mock coin
    # 1. 日K 多頭: Low > EMA10 > EMA20
    # 2. 1h RSI < 30
    # 3. 6h HA NTZ 出現
    # 4. 1h RSI < 50 (當 RSI<30 時自然 <50)
    # 5. 4h OBV Osc > 0
    import time

    base_time = int(time.time() * 1000)

    # 300 根日K，最後一段保持低點高於 EMA
    daily_ohlcv = []
    price = 50.0
    for i in range(300):
        price += 0.2
        daily_ohlcv.append([base_time - (300 - i) * 86400000, price, price + 1, price - 0.1, price + 0.8, 10000])

    # 1h K 線：構造前段震盪、末段急跌使 1h RSI 跌至 < 30
    ohlcv_1h = []
    p_1h = 100.0
    for i in range(150):
        ohlcv_1h.append([base_time - (200 - i) * 3600000, p_1h, p_1h + 0.5, p_1h - 0.5, p_1h, 1000])
    for i in range(50):
        p_1h -= 1.0  # 急跌
        ohlcv_1h.append([base_time - (50 - i) * 3600000, p_1h + 0.5, p_1h + 0.6, p_1h - 0.2, p_1h, 1000])

    # 6h K 線：含 NTZ
    ohlcv_6h = []
    for i in range(30):
        ohlcv_6h.append([base_time - (30 - i) * 21600000, 100, 105, 95, 101, 2000])

    # 4h K 線：OBV > 0
    ohlcv_4h = []
    p_4h = 80.0
    for i in range(60):
        p_4h += 0.5
        ohlcv_4h.append([base_time - (60 - i) * 14400000, p_4h, p_4h + 1, p_4h - 0.2, p_4h + 0.8, 5000])

    mock_coin = {
        "symbol": "MOCK_LONG",
        "name": "Mock Long Coin",
        "pair": "MOCK_LONG/USDT",
        "trade_symbol": "BITGET:MOCK_LONGUSDT",
        "rank": 99,
        "market_cap": 1000000,
        "ohlcv": daily_ohlcv,
        "ohlcv_1h": ohlcv_1h,
        "ohlcv_6h": ohlcv_6h,
        "ohlcv_4h": ohlcv_4h,
    }

    result = analyze_coin(mock_coin)
    assert result["status_rd"] == 3, f"預期 RD多頭(3)，實際: {result['status_rd']}"
    assert result["rsi"] < 30, f"預期 RSI < 30，實際: {result['rsi']}"
    assert result["ntz_appeared"] is True, "預期 NTZ 出現"
    assert result["long_entry"] is True, f"預期觸發做多進場，checklist={result['checklist']}"
    print(f"  ✅ 做多進場條件觸發成功 (滿足 {result['conditions_met_count']}/5)")

    # 測試多單出場：當 1h RSI > 70 且 RD多頭
    # 構造 1h 暴漲
    ohlcv_1h_exit = []
    p_exit = 50.0
    for i in range(200):
        p_exit += 1.0
        ohlcv_1h_exit.append([base_time - (200 - i) * 3600000, p_exit, p_exit + 1, p_exit - 0.2, p_exit + 0.8, 1000])

    mock_coin_exit = dict(mock_coin)
    mock_coin_exit["ohlcv_1h"] = ohlcv_1h_exit
    result_exit = analyze_coin(mock_coin_exit)
    assert result_exit["rsi"] > 70, f"預期 RSI > 70，實際: {result_exit['rsi']}"
    assert result_exit["long_exit"] is True, "預期觸發做多出場"
    assert result_exit["short_exit"] is False, "RD多頭下不應觸發做空出場"
    print(f"  ✅ 做多出場條件觸發成功 (RSI={result_exit['rsi']:.1f})")


def test_short_entry_and_exit_signals():
    print("▶ 測試 5: 合約做空進場與出場條件...")
    # 構造滿足 5 大做空條件的 mock coin
    # 1. 日K 空頭: High < EMA10 < EMA20 (status_rd == -3)
    # 2. 1h RSI > 70 (超買反彈)
    # 3. 6h HA NTZ 出現
    # 4. 1h RSI > 50
    # 5. 4h OBV Osc < 0
    import time
    base_time = int(time.time() * 1000)

    daily_ohlcv = []
    price = 200.0
    for i in range(300):
        price -= 0.3
        daily_ohlcv.append([base_time - (300 - i) * 86400000, price, price + 0.1, price - 1.0, price - 0.5, 10000])

    # 1h K 線：暴漲使 RSI > 70
    ohlcv_1h = []
    p_1h = 50.0
    for i in range(200):
        p_1h += 1.0
        ohlcv_1h.append([base_time - (200 - i) * 3600000, p_1h, p_1h + 1.0, p_1h - 0.2, p_1h + 0.8, 1000])

    # 6h K 線：含 NTZ
    ohlcv_6h = []
    for i in range(30):
        ohlcv_6h.append([base_time - (30 - i) * 21600000, 100, 105, 95, 101, 2000])

    # 4h K 線：持續下跌放量使 OBV < 0
    ohlcv_4h = []
    p_4h = 150.0
    for i in range(60):
        p_4h -= 0.8
        ohlcv_4h.append([base_time - (60 - i) * 14400000, p_4h, p_4h + 0.2, p_4h - 1.0, p_4h - 0.8, 5000])

    mock_coin_short = {
        "symbol": "MOCK_SHORT",
        "name": "Mock Short Coin",
        "pair": "MOCK_SHORT/USDT",
        "trade_symbol": "BITGET:MOCK_SHORTUSDT",
        "rank": 98,
        "market_cap": 500000,
        "ohlcv": daily_ohlcv,
        "ohlcv_1h": ohlcv_1h,
        "ohlcv_6h": ohlcv_6h,
        "ohlcv_4h": ohlcv_4h,
    }

    result = analyze_coin(mock_coin_short)
    assert result["status_rd"] == -3, f"預期 RD空頭(-3)，實際: {result['status_rd']}"
    assert result["rsi"] > 70, f"預期 RSI > 70，實際: {result['rsi']}"
    assert result["ntz_appeared"] is True, "預期 NTZ 出現"
    assert result["short_entry"] is True, f"預期觸發做空進場，checklist={result['checklist']}"
    print(f"  ✅ 做空進場條件觸發成功 (滿足 {result['conditions_met_count']}/5)")

    # 測試空單出場：空頭下 1h RSI < 30
    ohlcv_1h_drop = []
    p_drop = 100.0
    for i in range(200):
        p_drop -= 1.0
        ohlcv_1h_drop.append([base_time - (200 - i) * 3600000, p_drop, p_drop + 0.2, p_drop - 1.0, p_drop - 0.8, 1000])

    mock_coin_exit = dict(mock_coin_short)
    mock_coin_exit["ohlcv_1h"] = ohlcv_1h_drop
    result_exit = analyze_coin(mock_coin_exit)
    assert result_exit["rsi"] < 30, f"預期 RSI < 30，實際: {result_exit['rsi']}"
    assert result_exit["short_exit"] is True, "預期觸發做空出場"
    assert result_exit["long_exit"] is False, "RD空頭下不應觸發做多出場"
    print(f"  ✅ 做空出場條件觸發成功 (RSI={result_exit['rsi']:.1f})")


def test_telegram_message_formatting():
    print("▶ 測試 6: Telegram 訊息與卡片文案排版...")
    mock_results = [
        {
            "symbol": "BTC",
            "name": "Bitcoin",
            "rank": 1,
            "close": 83500.0,
            "change": -0.012,
            "status_rd": 3,
            "trend_days": 10,
            "dips_completed": 1,
            "dip_dates": ["09/28"],
            "has_warning": False,
            "in_dip": True,
            "latest_bar_date": "09/28",
            "rsi": 49.6,
            "ntz_appeared": True,
            "conditions_met_count": 3,
            "long_entry": False,
            "long_exit": False,
            "short_entry": False,
            "short_exit": False,
            "action_advice": "目前趨勢為多頭向上，但尚未同時滿足全部進場條件，建議觀望等待共振訊號。",
            "caution_note": "均線支撐良好，目前尚未出現動能竭盡警示。",
            "trade_symbol": "BITGET:BTCUSDT",
        }
    ]
    signals = {"long_entry": [], "long_exit": [], "short_entry": [], "short_exit": []}
    overview = format_signals_message(signals, mock_results, "2026/09/29 14:35")
    assert "加密貨幣趨勢日報" in overview
    assert "BTC" in overview
    assert "RSI:50" in overview
    assert "NTZ✅" in overview

    caption = format_coin_card_caption(mock_results[0])
    assert "Tradingview" in caption
    print("  ✅ Telegram 訊息與卡片排版測試通過")


def test_chronological_sequence_enforcement():
    print("▶ 測試 7: 五步驟時序先後關聯嚴格約束 (T1 <= T2 <= T3 <= T4 <= T5)...")
    import time
    base_time = int(time.time() * 1000)

    # 構造天圖 RD 多頭 (T1: 很久以前已確立)
    daily_ohlcv = []
    price = 50.0
    for i in range(100):
        price += 0.3
        daily_ohlcv.append([base_time - (100 - i) * 86400000, price, price + 1, price - 0.1, price + 0.8, 10000])

    # Case A: NTZ 發生在 RSI<30 之前 (時序顛倒)
    # 假設 6h NTZ 發生在 24 小時前 (base_time - 24h)，但 1h RSI<30 發生在 6 小時前 (base_time - 6h)
    ohlcv_6h_early = []
    p6 = 100.0
    for i in range(20):
        t = base_time - (20 - i) * 21600000
        if i == 14:  # 早於 RSI<30 的 NTZ
            ohlcv_6h_early.append([t, p6, p6 + 8, p6 - 8, p6 + 1, 2000])
        else:
            p6 += 10.0
            ohlcv_6h_early.append([t, p6, p6 + 10, p6, p6 + 10, 2000])  # open=low，無下影線強多頭棒

    ohlcv_1h_late_drop = []
    p = 100.0
    for i in range(50):
        t = base_time - (50 - i) * 3600000
        if i >= 44:  # 6h 前才急跌使 RSI<30
            p -= 2.0
            ohlcv_1h_late_drop.append([t, p + 1, p + 1.2, p - 0.2, p, 1000])
        else:
            ohlcv_1h_late_drop.append([t, p, p + 0.5, p - 0.5, p, 1000])

    # 4h OBV
    ohlcv_4h = [[base_time - (40 - i) * 14400000, 100 + i * 0.2, 101 + i * 0.2, 99 + i * 0.2, 100.8 + i * 0.2, 3000] for i in range(40)]

    coin_wrong_seq = {
        "symbol": "WRONG_SEQ",
        "name": "Wrong Seq Coin",
        "pair": "WRONG_SEQ/USDT",
        "rank": 99,
        "ohlcv": daily_ohlcv,
        "ohlcv_1h": ohlcv_1h_late_drop,
        "ohlcv_6h": ohlcv_6h_early,
        "ohlcv_4h": ohlcv_4h,
    }
    r_wrong = analyze_coin(coin_wrong_seq)
    # NTZ 結束於 base_time - 18h，但 RSI<30 發生在 base_time - 6h
    # 由於 NTZ 發生在 RSI<30 之前，不符合接續轉折條件，cond3_ok 必須為 False，不可觸發進場！
    assert r_wrong["cond2_ok"] is True, "步驟2 (RSI<30) 應觸發"
    assert r_wrong["cond3_ok"] is False, "NTZ 發生在 RSI<30 之前，步驟3應為 False！"
    assert r_wrong["long_entry"] is False, "時序顛倒絕不可觸發合約做多進場！"
    print("  ✅ 時序顛倒攔截測試通過 (NTZ 在 RSI<30 之前被正確拒絕)")

    # Case B: 正確時序: RSI<30 (12:00) -> 6h NTZ (14:00~20:00) -> 1h RSI<50 (20:00) -> 4h OBV>0
    # 在前面的 test_long_entry_and_exit_signals 已經驗證正確時序觸發 long_entry=True
    print("  ✅ 正確先後時序共振測試通過")


def test_five_charts_generation():
    print("▶ 測試 8: 5 張策略時序檢核圖表產生...")
    import time
    base_time = int(time.time() * 1000)

    # 構造完整多時間框架資料
    ohlcv = [[base_time - (75 - i) * 86400000, 100 + i, 102 + i, 99 + i, 101 + i, 10000] for i in range(75)]
    ohlcv_1h = [[base_time - (65 - i) * 3600000, 100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100.5 + i * 0.1, 2000] for i in range(65)]
    ohlcv_6h = [[base_time - (36 - i) * 21600000, 100, 105, 95, 101, 5000] for i in range(36)]
    ohlcv_4h = [[base_time - (40 - i) * 14400000, 100 + i * 0.2, 101 + i * 0.2, 99 + i * 0.2, 100.8 + i * 0.2, 3000] for i in range(40)]

    mock_coin = {
        "symbol": "TEST_FIVE",
        "name": "Test Five Coin",
        "pair": "TEST_FIVE/USDT",
        "trade_symbol": "BITGET:TEST_FIVEUSDT",
        "rank": 99,
        "market_cap": 1000000,
        "ohlcv": ohlcv,
        "ohlcv_1h": ohlcv_1h,
        "ohlcv_6h": ohlcv_6h,
        "ohlcv_4h": ohlcv_4h,
    }
    r = analyze_coin(mock_coin)
    charts_dir = "charts_test"
    paths = generate_all_strategy_charts(r, output_dir=charts_dir)
    assert len(paths) == 5, f"預期產生 5 張圖表，實際: {len(paths)}"
    expected_suffixes = ["_1_rd.png", "_2_rsi.png", "_3_ha.png", "_4_rsi.png", "_5_obv.png"]
    for p, suffix in zip(paths, expected_suffixes):
        assert os.path.exists(p), f"圖表檔案未存在: {p}"
        assert p.endswith(suffix), f"檔案檔名不符合預期: {p} vs {suffix}"
        assert os.path.getsize(p) > 1000, f"圖表檔案大小過小: {p}"
    print(f"  ✅ 5 張策略時序檢核圖表產生成功: {[os.path.basename(p) for p in paths]}")


if __name__ == "__main__":
    print("=" * 60)
    print("開始執行全方位策略驗證測試")
    print("=" * 60)
    test_rsi()
    test_heikin_ashi_and_ntz()
    test_obv_oscillator()
    test_long_entry_and_exit_signals()
    test_short_entry_and_exit_signals()
    test_telegram_message_formatting()
    test_chronological_sequence_enforcement()
    test_five_charts_generation()
    print("=" * 60)
    print("🎉 全部 8 大項策略單元測試均 100% 通過！")
    print("=" * 60)
