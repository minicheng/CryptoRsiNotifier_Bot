"""
合約波段策略 — 5 步時序驗證圖表產生模組
為符合條件之幣種分別產生 5 張專業 TradingView 暗黑風格圖表，依時間序列嚴格對應策略 5 大步驟：
  1. 步驟1: RD 趨勢 (天圖 / 日線 K 棒 + EMA10 + EMA20 + 成交量 + 狀態標註) -> {symbol}_1_rd.png
  2. 步驟2: RSI 超賣/超買 (1小時 K 棒 + RSI(14) 曲線，標註 RSI<30 或 >70 超賣打底點) -> {symbol}_2_rsi.png
  3. 步驟3: 平均K線 NTZ 轉折 (6小時 Heikin-Ashi K 棒，標註在步驟2之後出現的 NTZ 轉折棒) -> {symbol}_3_ha.png
  4. 步驟4: RSI 方向確認 (1小時 K 棒 + RSI(14) 曲線，標註在 NTZ 之後 RSI<50 或 >50 中軸蓄勢點) -> {symbol}_4_rsi.png
  5. 步驟5: OBV 動能確認 (4小時 K 棒 + OBV Oscillator 柱狀圖，標註數值與量縮判定) -> {symbol}_5_obv.png
"""

import os
import datetime
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei",   # Windows
    "Noto Sans CJK TC",     # Linux (apt: fonts-noto-cjk)
    "Noto Sans CJK SC",
    "SimHei",
    "Arial Unicode MS",
    "sans-serif",
]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from strategy import (
    calculate_ema,
    calculate_rsi_series,
    calculate_heikin_ashi,
    is_ntz,
    calculate_obv_oscillator_series,
)

# 顏色定義 (TradingView 暗黑風格)
BG_COLOR = "#131722"
PANEL_COLOR = "#1e222d"
GRID_COLOR = "#2a2e39"
TEXT_COLOR = "#d1d4dc"
MUTED_TEXT = "#848e9c"
BULL_COLOR = "#26a69a"       # 陽線綠
BEAR_COLOR = "#ef5350"       # 陰線紅
EMA10_COLOR = "#2962ff"      # EMA10 藍
EMA20_COLOR = "#f44336"      # EMA20 紅
RSI_COLOR = "#ab47bc"        # RSI 紫
GOLD_COLOR = "#f0b90b"       # 金色高亮標籤
CYAN_COLOR = "#00bcd4"       # 青色高亮標籤


def _format_chart_price(price):
    """圖表標題專用價格格式化"""
    if price is None:
        return "N/A"
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    elif price >= 0.001:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def _draw_candles(ax, x_indices, opens, highs, lows, closes, width=0.6, bull_color=BULL_COLOR, bear_color=BEAR_COLOR):
    """繪製標準 K 線棒"""
    for i, o, h, l, c in zip(x_indices, opens, highs, lows, closes):
        color = bull_color if c >= o else bear_color
        # 影線
        ax.plot([i, i], [l, h], color=color, linewidth=1.1, zorder=2)
        # 實體
        b_bottom = min(o, c)
        b_height = abs(c - o)
        if b_height == 0:
            b_height = (h - l) * 0.01 if (h - l) > 0 else 0.001
        rect = Rectangle(
            (i - width / 2.0, b_bottom),
            width,
            b_height,
            facecolor=color,
            edgecolor=color,
            linewidth=0.8,
            zorder=3,
        )
        ax.add_patch(rect)


# =====================================================================
# 1. 步驟 1: RD 趨勢 (天圖表示)
# =====================================================================
def generate_chart_step1_rd(coin_data, output_dir="charts", n_display=75):
    """
    產生圖 1: 步驟 1 RD 趨勢 (天圖表示)
    日 K 棒 + EMA10 + EMA20 + 日線成交量 + 狀態標註 (已過河拆橋天數、掉河次數)
    """
    ohlcv = coin_data.get("ohlcv", [])
    if not ohlcv or len(ohlcv) < 20:
        return None

    symbol = coin_data.get("symbol", "COIN")
    name = coin_data.get("name", symbol)
    close_price = coin_data.get("close", ohlcv[-1][4])
    change = coin_data.get("change", 0.0)
    status_rd = coin_data.get("status_rd", 3)
    trend_days = coin_data.get("trend_days", 0)
    dips_completed = coin_data.get("dips_completed", 0)
    cond1_ok = coin_data.get("cond1_ok", (status_rd in (3, -3)))

    display_bars = ohlcv[-n_display:] if len(ohlcv) >= n_display else ohlcv
    n_bars = len(display_bars)
    x_indices = list(range(n_bars))

    closes_all = [b[4] for b in ohlcv]
    full_ema10 = calculate_ema(closes_all, 10)[-n_bars:]
    full_ema20 = calculate_ema(closes_all, 20)[-n_bars:]

    opens = [b[1] for b in display_bars]
    highs = [b[2] for b in display_bars]
    lows = [b[3] for b in display_bars]
    closes = [b[4] for b in display_bars]
    vols = [b[5] for b in display_bars]
    tw_tz = datetime.timezone(datetime.timedelta(hours=8))
    dates = [datetime.datetime.fromtimestamp(b[0] / 1000, tz=tw_tz) for b in display_bars]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.2), gridspec_kw={"height_ratios": [3.5, 1.2]}, facecolor=BG_COLOR
    )

    # Subplot 1: 日K主圖
    ax1.set_facecolor(BG_COLOR)
    ax1.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    _draw_candles(ax1, x_indices, opens, highs, lows, closes)
    ax1.plot(x_indices, full_ema10, color=EMA10_COLOR, linewidth=1.6, label="EMA10")
    ax1.plot(x_indices, full_ema20, color=EMA20_COLOR, linewidth=1.6, label="EMA20")

    p_range = max(highs) - min(lows) if max(highs) > min(lows) else 1.0
    ax1.set_ylim(min(lows) - p_range * 0.06, max(highs) + p_range * 0.08)

    trend_tag = "RD多頭向上" if status_rd == 3 else "RD空頭向下"
    cond1_str = "[滿足]" if cond1_ok else "[未滿足]"

    ax1.set_title(
        f"【步驟1: RD趨勢 - 天圖】 {symbol} ({name}) | {_format_chart_price(close_price)} ({change*100:+.1f}%)\n"
        f"趨勢狀態: {trend_tag} | 已過河拆橋: {trend_days}天 | 掉河次數: {dips_completed}次 | 步驟1: {cond1_str}",
        color="#ffffff", fontsize=11, fontweight="bold", pad=8
    )

    ax1.yaxis.tick_right()
    ax1.yaxis.set_label_position("right")
    ax1.set_ylabel("Price (USDT)", color=MUTED_TEXT, fontsize=8.5)
    ax1.tick_params(colors=MUTED_TEXT, labelsize=8.5)
    ax1.legend(loc="upper left", facecolor=PANEL_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR, fontsize=8.5)

    # Subplot 2: 成交量
    ax2.set_facecolor(BG_COLOR)
    ax2.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    v_colors = [BULL_COLOR if c >= o else BEAR_COLOR for o, c in zip(opens, closes)]
    ax2.bar(x_indices, vols, color=v_colors, width=0.7, alpha=0.85)
    ax2.yaxis.tick_right()
    ax2.yaxis.set_label_position("right")
    ax2.set_ylabel("Volume", color=MUTED_TEXT, fontsize=8.5)
    ax2.tick_params(colors=MUTED_TEXT, labelsize=8.5)

    # X 軸時間標籤
    tick_step = max(n_bars // 8, 1)
    tick_positions = list(range(0, n_bars, tick_step))
    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels([dates[p].strftime("%m/%d") for p in tick_positions], rotation=25, color=MUTED_TEXT, fontsize=8.5)
    ax1.set_xticks([])

    plt.subplots_adjust(left=0.04, right=0.91, top=0.88, bottom=0.10, hspace=0.16)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.abspath(os.path.join(output_dir, f"{symbol}_1_rd.png"))
    plt.savefig(out_path, dpi=130, facecolor=BG_COLOR)
    plt.close(fig)
    return out_path


# =====================================================================
# 2. 步驟 2: RSI 超賣/超買確認 (1小時K表示)
# =====================================================================
def generate_chart_step2_rsi(coin_data, output_dir="charts", n_display=65):
    """
    產生圖 2: 步驟 2 RSI 超賣/超買 (1小時K表示)
    1小時 K 棒 + 1小時 RSI(14) 曲線
    明確呈現步驟 2: 多方 RSI<30（超賣打底）或空方 RSI>70（超買反彈）之時間點與數值
    """
    ohlcv_1h = coin_data.get("ohlcv_1h", [])
    if not ohlcv_1h or len(ohlcv_1h) < 20:
        return None

    symbol = coin_data.get("symbol", "COIN")
    name = coin_data.get("name", symbol)
    status_rd = coin_data.get("status_rd", 3)
    cond2_ok = coin_data.get("cond2_ok", False)
    cond2_time = coin_data.get("cond2_time")
    cond2_val = coin_data.get("cond2_val")
    cond2_idx_global = coin_data.get("cond2_idx")

    # 動態擴增顯示長度，確保步驟 2 觸發點完整呈現在視野內（左側保留 15 根 K 棒餘裕）
    if cond2_idx_global is not None:
        bars_needed = (len(ohlcv_1h) - cond2_idx_global) + 15
        n_display = max(n_display, min(bars_needed, len(ohlcv_1h)))

    display_bars = ohlcv_1h[-n_display:] if len(ohlcv_1h) >= n_display else ohlcv_1h
    n_bars = len(display_bars)
    x_indices = list(range(n_bars))

    closes_all = [b[4] for b in ohlcv_1h]
    rsi_all = calculate_rsi_series(closes_all, 14)
    rsi_disp = rsi_all[-n_bars:]

    opens = [b[1] for b in display_bars]
    highs = [b[2] for b in display_bars]
    lows = [b[3] for b in display_bars]
    closes = [b[4] for b in display_bars]
    tw_tz = datetime.timezone(datetime.timedelta(hours=8))
    dates = [datetime.datetime.fromtimestamp(b[0] / 1000, tz=tw_tz) for b in display_bars]

    cond2_disp_idx = None
    if cond2_idx_global is not None:
        offset = len(ohlcv_1h) - n_bars
        if cond2_idx_global >= offset:
            cond2_disp_idx = cond2_idx_global - offset

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.4), gridspec_kw={"height_ratios": [3.2, 1.8]}, facecolor=BG_COLOR
    )

    # Subplot 1: 1h K 線主圖
    ax1.set_facecolor(BG_COLOR)
    ax1.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    _draw_candles(ax1, x_indices, opens, highs, lows, closes)
    p_range = max(highs) - min(lows) if max(highs) > min(lows) else 1.0
    ax1.set_ylim(min(lows) - p_range * 0.12, max(highs) + p_range * 0.12)

    # 標記條件 2 垂線與註解
    if cond2_disp_idx is not None and 0 <= cond2_disp_idx < n_bars:
        ax1.axvline(cond2_disp_idx, color=CYAN_COLOR, linestyle="--", linewidth=1.6, alpha=0.9)
        cond2_label = f"步驟2觸發點: {cond2_time}\nRSI={cond2_val:.1f}" if cond2_val is not None else f"步驟2: {cond2_time}"
        ax1.annotate(
            cond2_label,
            xy=(cond2_disp_idx, lows[cond2_disp_idx]),
            xytext=(cond2_disp_idx, lows[cond2_disp_idx] - p_range * 0.08),
            bbox=dict(boxstyle="round,pad=0.35", fc=PANEL_COLOR, ec=CYAN_COLOR, lw=1.2),
            arrowprops=dict(arrowstyle="->", color=CYAN_COLOR, lw=1.2),
            color=CYAN_COLOR, fontsize=8.5, fontweight="bold", ha="center"
        )

    cond2_target = "多方條件: RSI<30 (超賣打底)" if status_rd == 3 else "空方條件: RSI>70 (超買反彈)"
    cond2_status = f"[滿足] ({cond2_time} RSI={cond2_val:.1f})" if cond2_ok and cond2_time else "[未滿足]"

    ax1.set_title(
        f"【步驟2: RSI超賣/超買 - 1小時K】 {symbol} ({name})\n"
        f"{cond2_target}  |  步驟2: {cond2_status}",
        color="#ffffff", fontsize=11, fontweight="bold", pad=8
    )
    ax1.yaxis.tick_right()
    ax1.yaxis.set_label_position("right")
    ax1.set_ylabel("1h Price", color=MUTED_TEXT, fontsize=8.5)
    ax1.tick_params(colors=MUTED_TEXT, labelsize=8.5)
    ax1.set_xticks([])

    # Subplot 2: RSI(14) 指標子圖
    ax2.set_facecolor(BG_COLOR)
    ax2.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    ax2.plot(x_indices, rsi_disp, color=RSI_COLOR, linewidth=1.8, label="RSI(14)")

    ax2.axhline(70, color=BEAR_COLOR, linestyle="--", linewidth=0.9, alpha=0.7)
    ax2.axhline(50, color="#787b86", linestyle=":", linewidth=0.8, alpha=0.7)
    ax2.axhline(30, color=BULL_COLOR, linestyle="--", linewidth=0.9, alpha=0.7)
    ax2.axhspan(70, 100, color=BEAR_COLOR, alpha=0.10)
    ax2.axhspan(0, 30, color=BULL_COLOR, alpha=0.10)

    if cond2_disp_idx is not None and 0 <= cond2_disp_idx < n_bars:
        ax2.axvline(cond2_disp_idx, color=CYAN_COLOR, linestyle=":", linewidth=1.6, alpha=0.85)
        ax2.scatter([cond2_disp_idx], [rsi_disp[cond2_disp_idx]], color=CYAN_COLOR, s=50, zorder=5)

    ax2.set_ylim(0, 100)
    ax2.yaxis.tick_right()
    ax2.yaxis.set_label_position("right")
    ax2.set_ylabel("RSI(1h)", color=MUTED_TEXT, fontsize=8.5)
    ax2.tick_params(colors=MUTED_TEXT, labelsize=8.5)

    tick_step = max(n_bars // 7, 1)
    tick_positions = list(range(0, n_bars, tick_step))
    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels([dates[p].strftime("%m/%d %H:%M") for p in tick_positions], rotation=25, color=MUTED_TEXT, fontsize=8.5)

    plt.subplots_adjust(left=0.04, right=0.91, top=0.88, bottom=0.10, hspace=0.18)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.abspath(os.path.join(output_dir, f"{symbol}_2_rsi.png"))
    plt.savefig(out_path, dpi=130, facecolor=BG_COLOR)
    plt.close(fig)
    return out_path


# =====================================================================
# 3. 步驟 3: 平均K線 NTZ 轉折 (6小時平均K線圖表示)
# =====================================================================
def generate_chart_step3_ha(coin_data, output_dir="charts", n_display=36):
    """
    產生圖 3: 步驟 3 平均K線趨勢 (6小時平均K線圖表示)
    6小時 Heikin-Ashi K 棒，標註在步驟 2 之後出現的 NTZ 轉折 K 棒
    額外標註步驟 2 發生的時間參考線
    """
    ohlcv_6h = coin_data.get("ohlcv_6h", [])
    if not ohlcv_6h or len(ohlcv_6h) < 10:
        return None

    symbol = coin_data.get("symbol", "COIN")
    name = coin_data.get("name", symbol)
    cond2_time = coin_data.get("cond2_time", "")
    cond2_ts = coin_data.get("cond2_ts")
    cond3_ok = coin_data.get("cond3_ok", False)
    cond3_time = coin_data.get("cond3_time", "")
    cond3_idx = coin_data.get("cond3_idx")

    # 動態擴增顯示長度，確保步驟 2 觸發與步驟 3 NTZ 均完整呈現在視野內
    target_ts = coin_data.get("cond2_open_ts") or cond2_ts
    earliest_6h_idx = cond3_idx
    if target_ts:
        for i, bar in enumerate(ohlcv_6h):
            bar_start_ts = bar[0]
            bar_end_ts = bar_start_ts + 6 * 3600 * 1000
            if bar_start_ts <= target_ts <= bar_end_ts:
                if earliest_6h_idx is None or i < earliest_6h_idx:
                    earliest_6h_idx = i
                break
    if earliest_6h_idx is not None:
        bars_needed = (len(ohlcv_6h) - earliest_6h_idx) + 8
        n_display = max(n_display, min(bars_needed, len(ohlcv_6h)))

    ha_bars_all = calculate_heikin_ashi(ohlcv_6h)
    display_ha = ha_bars_all[-n_display:] if len(ha_bars_all) >= n_display else ha_bars_all
    display_raw = ohlcv_6h[-n_display:] if len(ohlcv_6h) >= n_display else ohlcv_6h
    n_bars = len(display_ha)
    x_indices = list(range(n_bars))

    opens = [b["open"] for b in display_ha]
    highs = [b["high"] for b in display_ha]
    lows = [b["low"] for b in display_ha]
    closes = [b["close"] for b in display_ha]
    tw_tz = datetime.timezone(datetime.timedelta(hours=8))
    dates = [datetime.datetime.fromtimestamp(b[0] / 1000, tz=tw_tz) for b in display_raw]

    fig, ax1 = plt.subplots(1, 1, figsize=(11, 5.8), facecolor=BG_COLOR)
    ax1.set_facecolor(BG_COLOR)
    ax1.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)

    _draw_candles(ax1, x_indices, opens, highs, lows, closes, width=0.65)
    p_range = max(highs) - min(lows) if max(highs) > min(lows) else 1.0
    ax1.set_ylim(min(lows) - p_range * 0.16, max(highs) + p_range * 0.18)

    # ---- (A) 步驟 2 時間參考線 (青色虛線，置於頂端) ----
    cond2_ref_idx = None
    if target_ts:
        for i, bar in enumerate(display_raw):
            bar_start_ts = bar[0]
            bar_end_ts = bar_start_ts + 6 * 3600 * 1000
            if bar_start_ts <= target_ts <= bar_end_ts:
                cond2_ref_idx = i
                break
            elif bar_start_ts > target_ts:
                cond2_ref_idx = max(0, i - 1)
                break
    if cond2_ref_idx is not None and 0 <= cond2_ref_idx < n_bars:
        ax1.axvline(cond2_ref_idx, color=CYAN_COLOR, linestyle="--", linewidth=1.6, alpha=0.9)
        ax1.annotate(
            f"步驟2: RSI觸發\n({cond2_time})",
            xy=(cond2_ref_idx, max(highs)),
            xytext=(cond2_ref_idx, max(highs) + p_range * 0.08),
            bbox=dict(boxstyle="round,pad=0.35", fc=PANEL_COLOR, ec=CYAN_COLOR, lw=1.2),
            arrowprops=dict(arrowstyle="->", color=CYAN_COLOR, lw=1.2),
            color=CYAN_COLOR, fontsize=8.5, fontweight="bold", ha="center"
        )

    # ---- (B) 醒目標記命中的 NTZ 轉折棒 (步驟 3 確認，置於底端) ----
    target_disp_idx = None
    if cond3_idx is not None:
        offset = len(ohlcv_6h) - n_bars
        if cond3_idx >= offset:
            target_disp_idx = cond3_idx - offset

    if target_disp_idx is not None and 0 <= target_disp_idx < n_bars:
        ax1.axvline(target_disp_idx, color=GOLD_COLOR, linestyle="--", linewidth=1.6, alpha=0.9)
        ax1.scatter([target_disp_idx], [lows[target_disp_idx] - p_range * 0.02],
                    marker="D", color=GOLD_COLOR, s=90, zorder=6, edgecolors="white", linewidth=1.2)
        ax1.annotate(
            f"步驟3: NTZ轉折確認\n({cond3_time})",
            xy=(target_disp_idx, lows[target_disp_idx] - p_range * 0.02),
            xytext=(target_disp_idx, lows[target_disp_idx] - p_range * 0.10),
            bbox=dict(boxstyle="round,pad=0.35", fc=PANEL_COLOR, ec=GOLD_COLOR, lw=1.3),
            arrowprops=dict(arrowstyle="->", color=GOLD_COLOR, lw=1.3),
            color=GOLD_COLOR, fontsize=8.5, fontweight="bold", ha="center"
        )

    cond3_status = f"[滿足] ({cond3_time})" if cond3_ok and cond3_time else "[未滿足]"

    ax1.set_title(
        f"【步驟3: 平均K線NTZ轉折 - 6小時HA】 {symbol} ({name})\n"
        f"目標: 出現NTZ轉折棒(接續步驟2之後) | 步驟3: {cond3_status}",
        color="#ffffff", fontsize=11, fontweight="bold", pad=10
    )

    ax1.yaxis.tick_right()
    ax1.yaxis.set_label_position("right")
    ax1.set_ylabel("6h HA Price", color=MUTED_TEXT, fontsize=8.5)
    ax1.tick_params(colors=MUTED_TEXT, labelsize=8.5)

    tick_step = max(n_bars // 7, 1)
    tick_positions = list(range(0, n_bars, tick_step))
    ax1.set_xticks(tick_positions)
    ax1.set_xticklabels([dates[p].strftime("%m/%d %H:%M") for p in tick_positions], rotation=25, color=MUTED_TEXT, fontsize=8.5)

    plt.subplots_adjust(left=0.04, right=0.91, top=0.86, bottom=0.12)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.abspath(os.path.join(output_dir, f"{symbol}_3_ha.png"))
    plt.savefig(out_path, dpi=130, facecolor=BG_COLOR)
    plt.close(fig)
    return out_path


# =====================================================================
# 4. 步驟 4: RSI 方向確認 (1小時K表示)
# =====================================================================
def generate_chart_step4_rsi(coin_data, output_dir="charts", n_display=65):
    """
    產生圖 4: 步驟 4 RSI 方向確認 (1小時K表示)
    1小時 K 棒 + 1小時 RSI(14) 曲線
    著重呈現 50 中軸線與多空方向判定（多方 RSI<50 蓄勢 / 空方 RSI>50 蓄勢）
    額外標註步驟 3 NTZ 發生的時間參考線
    """
    ohlcv_1h = coin_data.get("ohlcv_1h", [])
    if not ohlcv_1h or len(ohlcv_1h) < 20:
        return None

    symbol = coin_data.get("symbol", "COIN")
    name = coin_data.get("name", symbol)
    status_rd = coin_data.get("status_rd", 3)
    cond3_time = coin_data.get("cond3_time", "")
    cond3_ts = coin_data.get("cond3_ts")
    cond4_ok = coin_data.get("cond4_ok", False)
    cond4_time = coin_data.get("cond4_time", "")
    cond4_val = coin_data.get("cond4_val", coin_data.get("rsi", 50.0))
    cond4_idx_global = coin_data.get("cond4_idx")

    # 動態擴增顯示長度，確保步驟 3 NTZ 與步驟 4 RSI 確認棒均完整呈現在視野內
    earliest_idx = cond4_idx_global
    if cond3_ts:
        for i, bar in enumerate(ohlcv_1h):
            bar_ts = bar[0]
            if bar_ts >= cond3_ts:
                if earliest_idx is None or i < earliest_idx:
                    earliest_idx = i
                break
    if earliest_idx is not None:
        bars_needed = (len(ohlcv_1h) - earliest_idx) + 15
        n_display = max(n_display, min(bars_needed, len(ohlcv_1h)))

    display_bars = ohlcv_1h[-n_display:] if len(ohlcv_1h) >= n_display else ohlcv_1h
    n_bars = len(display_bars)
    x_indices = list(range(n_bars))

    closes_all = [b[4] for b in ohlcv_1h]
    rsi_all = calculate_rsi_series(closes_all, 14)
    rsi_disp = rsi_all[-n_bars:]

    opens = [b[1] for b in display_bars]
    highs = [b[2] for b in display_bars]
    lows = [b[3] for b in display_bars]
    closes = [b[4] for b in display_bars]
    tw_tz = datetime.timezone(datetime.timedelta(hours=8))
    dates = [datetime.datetime.fromtimestamp(b[0] / 1000, tz=tw_tz) for b in display_bars]

    # 計算步驟 4 確認棒的顯示位置
    cond4_disp_idx = None
    if cond4_idx_global is not None:
        offset = len(ohlcv_1h) - n_bars
        if cond4_idx_global >= offset:
            cond4_disp_idx = cond4_idx_global - offset
    if cond4_disp_idx is None:
        cond4_disp_idx = n_bars - 1  # 備用: 使用最新 K 棒

    # 計算步驟 3 NTZ 參考位置 (在 1h K 中找接續的 02:00 K 棒)
    cond3_ref_idx = None
    if cond3_ts:
        for i, bar in enumerate(display_bars):
            bar_ts = bar[0]
            if bar_ts >= cond3_ts:
                cond3_ref_idx = i
                break

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.4), gridspec_kw={"height_ratios": [3.2, 1.8]}, facecolor=BG_COLOR
    )

    # Subplot 1: 1h K 線主圖
    ax1.set_facecolor(BG_COLOR)
    ax1.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    _draw_candles(ax1, x_indices, opens, highs, lows, closes)
    p_range = max(highs) - min(lows) if max(highs) > min(lows) else 1.0
    ax1.set_ylim(min(lows) - p_range * 0.14, max(highs) + p_range * 0.18)

    # ---- (A) 步驟 3 NTZ 時間參考線 (青色虛線，置於頂端) ----
    if cond3_ref_idx is not None and 0 <= cond3_ref_idx < n_bars:
        ax1.axvline(cond3_ref_idx, color=CYAN_COLOR, linestyle="--", linewidth=1.6, alpha=0.9)
        ax1.annotate(
            f"步驟3: NTZ確認\n({cond3_time})",
            xy=(cond3_ref_idx, max(highs)),
            xytext=(cond3_ref_idx, max(highs) + p_range * 0.08),
            bbox=dict(boxstyle="round,pad=0.35", fc=PANEL_COLOR, ec=CYAN_COLOR, lw=1.2),
            arrowprops=dict(arrowstyle="->", color=CYAN_COLOR, lw=1.2),
            color=CYAN_COLOR, fontsize=8.5, fontweight="bold", ha="center"
        )

    # ---- (B) 步驟 4 確認垂線與註解 (金色虛線，置於底端) ----
    if cond4_disp_idx is not None and 0 <= cond4_disp_idx < n_bars:
        ax1.axvline(cond4_disp_idx, color=GOLD_COLOR, linestyle="--", linewidth=1.6, alpha=0.9)
        ax1.annotate(
            f"步驟4確認點: {cond4_time}\nRSI={cond4_val:.1f}",
            xy=(cond4_disp_idx, lows[cond4_disp_idx]),
            xytext=(cond4_disp_idx, lows[cond4_disp_idx] - p_range * 0.08),
            bbox=dict(boxstyle="round,pad=0.35", fc=PANEL_COLOR, ec=GOLD_COLOR, lw=1.2),
            arrowprops=dict(arrowstyle="->", color=GOLD_COLOR, lw=1.2),
            color=GOLD_COLOR, fontsize=8.5, fontweight="bold", ha="center"
        )

    target_req = "多方條件: RSI<50 (蓄勢起步中軸有利)" if status_rd == 3 else "空方條件: RSI>50 (反彈蓄勢中軸有利)"
    cond4_dir_ok = (cond4_val < 50) if status_rd == 3 else (cond4_val > 50)
    if cond4_ok:
        cond4_status = f"[滿足] ({cond4_time} RSI={cond4_val:.1f})"
    elif cond4_dir_ok:
        cond4_status = f"[指標符合] ({cond4_time} RSI={cond4_val:.1f})"
    else:
        cond4_status = f"[未滿足] (RSI={cond4_val:.1f})"

    ax1.set_title(
        f"【步驟4: RSI方向確認 - 1小時K】 {symbol} ({name})\n"
        f"{target_req}  |  步驟4: {cond4_status}",
        color="#ffffff", fontsize=11, fontweight="bold", pad=8
    )
    ax1.yaxis.tick_right()
    ax1.yaxis.set_label_position("right")
    ax1.set_ylabel("1h Price", color=MUTED_TEXT, fontsize=8.5)
    ax1.tick_params(colors=MUTED_TEXT, labelsize=8.5)
    ax1.set_xticks([])

    # Subplot 2: RSI(14) 指標子圖 (著重 50 中軸)
    ax2.set_facecolor(BG_COLOR)
    ax2.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    ax2.plot(x_indices, rsi_disp, color=RSI_COLOR, linewidth=1.8, label="RSI(14)")

    # 醒目標示 50 中軸線
    ax2.axhline(50, color=GOLD_COLOR, linestyle="--", linewidth=1.5, alpha=0.9, label="中軸 50")
    ax2.axhline(70, color=BEAR_COLOR, linestyle=":", linewidth=0.8, alpha=0.6)
    ax2.axhline(30, color=BULL_COLOR, linestyle=":", linewidth=0.8, alpha=0.6)

    # 標示有利區域
    if status_rd == 3:
        ax2.axhspan(0, 50, color=BULL_COLOR, alpha=0.08, label="多方有利區 (<50)")
    else:
        ax2.axhspan(50, 100, color=BEAR_COLOR, alpha=0.08, label="空方有利區 (>50)")

    # 步驟 3 參考線 (RSI 子圖)
    if cond3_ref_idx is not None and 0 <= cond3_ref_idx < n_bars:
        ax2.axvline(cond3_ref_idx, color=CYAN_COLOR, linestyle=":", linewidth=1.2, alpha=0.6)

    # 步驟 4 確認標記 (RSI 子圖)
    if cond4_disp_idx is not None and 0 <= cond4_disp_idx < n_bars:
        ax2.axvline(cond4_disp_idx, color=GOLD_COLOR, linestyle="--", linewidth=1.5, alpha=0.85)
        ax2.scatter([cond4_disp_idx], [rsi_disp[cond4_disp_idx]], color=GOLD_COLOR, s=50, zorder=5)

    ax2.set_ylim(0, 100)
    ax2.yaxis.tick_right()
    ax2.yaxis.set_label_position("right")
    ax2.set_ylabel("RSI(1h)", color=MUTED_TEXT, fontsize=8.5)
    ax2.tick_params(colors=MUTED_TEXT, labelsize=8.5)
    ax2.legend(loc="upper left", facecolor=PANEL_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR, fontsize=8.0)

    tick_step = max(n_bars // 7, 1)
    tick_positions = list(range(0, n_bars, tick_step))
    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels([dates[p].strftime("%m/%d %H:%M") for p in tick_positions], rotation=25, color=MUTED_TEXT, fontsize=8.5)

    plt.subplots_adjust(left=0.04, right=0.91, top=0.88, bottom=0.10, hspace=0.18)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.abspath(os.path.join(output_dir, f"{symbol}_4_rsi.png"))
    plt.savefig(out_path, dpi=130, facecolor=BG_COLOR)
    plt.close(fig)
    return out_path


# =====================================================================
# 5. 步驟 5: OBV 動能確認 (天圖日K OBV_Oscillator 指標表示)
# =====================================================================
def generate_chart_step5_obv(coin_data, output_dir="charts", n_display=75):
    """
    產生圖 5: 步驟 5 OBV 動能確認 (天圖日K OBV_Oscillator 指標表示)
    天圖日 K 棒 + 日K OBV Oscillator 柱狀圖，標示最新值、前一根值及量縮判定
    """
    ohlcv = coin_data.get("ohlcv", [])
    if not ohlcv or len(ohlcv) < 22:
        return None

    symbol = coin_data.get("symbol", "COIN")
    name = coin_data.get("name", symbol)
    status_rd = coin_data.get("status_rd", 3)
    curr_osc = coin_data.get("obv_osc", 0.0)
    prev_osc = coin_data.get("obv_osc_prev", 0.0)
    is_shrinking = coin_data.get("obv_is_shrinking", False)
    cond5_ok = coin_data.get("cond5_ok", False)
    cond5_time = coin_data.get("cond5_time", "")
    cond4_time = coin_data.get("cond4_time", "")
    cond5_idx = coin_data.get("cond5_idx")

    # 動態擴增顯示長度，確保步驟 5 確認點完整呈現在視野內（左側保留 15 根 K 棒餘裕）
    if cond5_idx is not None:
        bars_needed = (len(ohlcv) - cond5_idx) + 15
        n_display = max(n_display, min(bars_needed, len(ohlcv)))

    display_bars = ohlcv[-n_display:] if len(ohlcv) >= n_display else ohlcv
    n_bars = len(display_bars)
    x_indices = list(range(n_bars))

    osc_all = calculate_obv_oscillator_series(ohlcv, 21)  # 天圖 OBV
    osc_disp = osc_all[-n_bars:]

    opens = [b[1] for b in display_bars]
    highs = [b[2] for b in display_bars]
    lows = [b[3] for b in display_bars]
    closes = [b[4] for b in display_bars]
    tw_tz = datetime.timezone(datetime.timedelta(hours=8))
    dates = [datetime.datetime.fromtimestamp(b[0] / 1000, tz=tw_tz) for b in display_bars]

    cond5_disp_idx = None
    if cond5_idx is not None:
        offset = len(ohlcv) - n_bars
        if cond5_idx >= offset:
            cond5_disp_idx = cond5_idx - offset
    if cond5_disp_idx is None:
        cond5_disp_idx = n_bars - 1

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.2), gridspec_kw={"height_ratios": [3.0, 2.0]}, facecolor=BG_COLOR
    )

    # Subplot 1: 天圖日K 線主圖
    ax1.set_facecolor(BG_COLOR)
    ax1.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    _draw_candles(ax1, x_indices, opens, highs, lows, closes)
    p_range = max(highs) - min(lows) if max(highs) > min(lows) else 1.0
    ax1.set_ylim(min(lows) - p_range * 0.12, max(highs) + p_range * 0.12)

    # 在主圖上標註步驟 5 當時確認點
    if cond5_disp_idx is not None and 0 <= cond5_disp_idx < n_bars:
        ax1.axvline(cond5_disp_idx, color=GOLD_COLOR, linestyle="--", linewidth=1.6, alpha=0.9)
        c5_label = f"步驟5: 當時天圖OBV確認點 ({cond5_time})\n接續步驟4 ({cond4_time})" if cond4_time else f"步驟5: 天圖OBV確認 ({cond5_time})"
        ax1.annotate(
            c5_label,
            xy=(cond5_disp_idx, lows[cond5_disp_idx]),
            xytext=(cond5_disp_idx, lows[cond5_disp_idx] - p_range * 0.08),
            bbox=dict(boxstyle="round,pad=0.35", fc=PANEL_COLOR, ec=GOLD_COLOR, lw=1.2),
            arrowprops=dict(arrowstyle="->", color=GOLD_COLOR, lw=1.2),
            color=GOLD_COLOR, fontsize=8.5, fontweight="bold", ha="center"
        )

    target_req = "多方條件: OBV>0 或 量縮" if status_rd == 3 else "空方條件: OBV<0 或 量縮"
    shrink_text = "量縮: [是] (|當前| < |前值|)" if is_shrinking else "量縮: [否]"
    obv_val_ok = (curr_osc > 0) if status_rd == 3 else (curr_osc < 0)
    momentum_ok = obv_val_ok or is_shrinking
    if cond5_ok:
        cond5_status = "[滿足] (" + ("OBV>0" if obv_val_ok else "量縮") + ")"
    elif momentum_ok:
        cond5_status = "[指標符合] (" + ("OBV>0" if obv_val_ok else "量縮") + ")"
    else:
        cond5_status = "[未滿足]"

    ax1.set_title(
        f"【步驟5: OBV動能確認 - 天圖 OBV Oscillator】 {symbol} ({name})\n"
        f"{target_req}  |  當時OBV({cond5_time}): {curr_osc:+,.0f} (前值: {prev_osc:+,.0f})  |  {shrink_text}  |  步驟5: {cond5_status}",
        color="#ffffff", fontsize=11, fontweight="bold", pad=8
    )
    ax1.yaxis.tick_right()
    ax1.yaxis.set_label_position("right")
    ax1.set_ylabel("Daily Price", color=MUTED_TEXT, fontsize=8.5)
    ax1.tick_params(colors=MUTED_TEXT, labelsize=8.5)
    ax1.set_xticks([])

    # Subplot 2: OBV Oscillator 柱狀圖
    ax2.set_facecolor(BG_COLOR)
    ax2.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    bar_colors = [BULL_COLOR if val >= 0 else BEAR_COLOR for val in osc_disp]
    ax2.bar(x_indices, osc_disp, color=bar_colors, width=0.7, alpha=0.85)
    ax2.axhline(0, color="#ffffff", linestyle="--", linewidth=0.8, alpha=0.7)

    # 在柱狀圖上標記步驟 5 當時的 OBV 柱體
    if cond5_disp_idx is not None and 0 <= cond5_disp_idx < n_bars:
        ax2.axvline(cond5_disp_idx, color=GOLD_COLOR, linestyle="--", linewidth=1.5, alpha=0.85)
        osc_val = osc_disp[cond5_disp_idx]
        offset_y = (max(abs(osc_val), 100) * (0.35 if osc_val >= 0 else -0.55))
        ax2.annotate(
            f"當時OBV: {osc_val:+,.0f}",
            xy=(cond5_disp_idx, osc_val),
            xytext=(cond5_disp_idx, osc_val + offset_y),
            color=GOLD_COLOR, fontsize=8.5, fontweight="bold", ha="center",
            arrowprops=dict(arrowstyle="->", color=GOLD_COLOR, lw=1.1)
        )

    ax2.yaxis.tick_right()
    ax2.yaxis.set_label_position("right")
    ax2.set_ylabel("OBV Osc", color=MUTED_TEXT, fontsize=8.5)
    ax2.tick_params(colors=MUTED_TEXT, labelsize=8.5)

    tick_step = max(n_bars // 7, 1)
    tick_positions = list(range(0, n_bars, tick_step))
    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels([dates[p].strftime("%m/%d") for p in tick_positions], rotation=25, color=MUTED_TEXT, fontsize=8.5)

    plt.subplots_adjust(left=0.04, right=0.91, top=0.88, bottom=0.10, hspace=0.18)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.abspath(os.path.join(output_dir, f"{symbol}_5_obv.png"))
    plt.savefig(out_path, dpi=130, facecolor=BG_COLOR)
    plt.close(fig)
    return out_path


# =====================================================================
# 6. 整合產生全部 5 張時序檢核圖表
# =====================================================================
def generate_all_strategy_charts(coin_data, output_dir="charts"):
    """
    為指定幣種依序產生 5 張策略時序檢核圖表：
      1. 步驟1: RD 趨勢 (天圖) -> {symbol}_1_rd.png
      2. 步驟2: RSI 超賣/超買 (1小時K) -> {symbol}_2_rsi.png
      3. 步驟3: 平均K線 NTZ 轉折 (6小時Heikin-Ashi) -> {symbol}_3_ha.png
      4. 步驟4: RSI 方向確認 (1小時K) -> {symbol}_4_rsi.png
      5. 步驟5: OBV 動能確認 (4小時OBV_Oscillator) -> {symbol}_5_obv.png

    Returns:
        list[str]: 5 個圖表檔案的本機絕對路徑列表（過濾掉失敗者）
    """
    charts = []
    p1 = generate_chart_step1_rd(coin_data, output_dir=output_dir)
    if p1 and os.path.exists(p1):
        charts.append(p1)

    p2 = generate_chart_step2_rsi(coin_data, output_dir=output_dir)
    if p2 and os.path.exists(p2):
        charts.append(p2)

    p3 = generate_chart_step3_ha(coin_data, output_dir=output_dir)
    if p3 and os.path.exists(p3):
        charts.append(p3)

    p4 = generate_chart_step4_rsi(coin_data, output_dir=output_dir)
    if p4 and os.path.exists(p4):
        charts.append(p4)

    p5 = generate_chart_step5_obv(coin_data, output_dir=output_dir)
    if p5 and os.path.exists(p5):
        charts.append(p5)

    return charts


# 向下相容別名
generate_rd_chart = generate_chart_step1_rd
generate_rsi_chart = generate_chart_step2_rsi
generate_ha_chart = generate_chart_step3_ha
generate_obv_chart = generate_chart_step5_obv
generate_coin_chart = generate_chart_step1_rd
