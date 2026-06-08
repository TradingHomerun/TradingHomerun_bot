"""
7-Indikator Signal Engine
==========================
Jeder Indikator ist einer eigenen Kategorie zugeordnet und
misst etwas fundamental anderes — kein Überlappen, kein Rauschen.

Gewichtung (Summe = 100%):
    1. EMA-Trend          25%  ← Wichtigster: bestimmt die Grundrichtung
    2. MACD               20%  ← Trendwechsel frühzeitig erkennen
    3. RSI                15%  ← Extrempunkte (Einstieg/Ausstieg)
    4. Bollinger Bands    15%  ← Volatilitäts-Ausbrüche
    5. OBV                10%  ← Volumen bestätigt Preisbewegung
    6. Pivot Points       10%  ← Echte Support/Resistance Level
    7. Fear & Greed        5%  ← Sentiment (Kontraindikator)

Signal-Entscheidung (gewichteter Score 0–100):
    ≥ 65  →  KAUFEN   (stark bullish)
    ≤ 35  →  VERKAUFEN (stark bearish)
    sonst →  NEUTRAL
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalResult:
    signal:         str          # KAUFEN | VERKAUFEN | NEUTRAL
    score:          int          # Anzahl aktiver bullisher/bearisher Signale
    max_score:      int          # Wie viele Indikatoren hatten Daten
    confidence:     int          # 0–100 gewichteter Score
    active_signals: list[str]    # Beschreibungen der ausgelösten Signale
    details:        dict         # Pro-Indikator Erklärungen


# ─── Gewichte ────────────────────────────────────────────────────────────────
WEIGHTS = {
    "ema":        25,
    "macd":       20,
    "rsi":        15,
    "bollinger":  15,
    "obv":        10,
    "pivot":      10,
    "fear_greed":  5,
}


def evaluate_signals(p) -> SignalResult:
    """
    Wertet alle 7 Indikatoren aus.
    Gibt +weight für bullish, -weight für bearish, 0 für neutral/kein Wert.
    """
    weighted_score = 0   # Summe der Gewichte: positiv = bullish, negativ = bearish
    total_weight   = 0   # Summe der Gewichte aller verfügbaren Indikatoren
    bullish_count  = 0
    bearish_count  = 0
    active         = []
    details        = {}

    # ──────────────────────────────────────────────────────────────────────────
    # 1. EMA-TREND (Gewicht: 25%)
    # Logik: Preis über EMA20 > EMA50 > EMA200 = starker Aufwärtstrend
    #        "Golden Stack" — alle drei EMAs aufsteigend ausgerichtet
    # ──────────────────────────────────────────────────────────────────────────
    if p.ema20 and p.ema50 and p.ema200:
        total_weight += WEIGHTS["ema"]
        price = p.close

        bullish_stack = price > p.ema20 > p.ema50 > p.ema200
        bearish_stack = price < p.ema20 < p.ema50 < p.ema200

        if bullish_stack:
            weighted_score += WEIGHTS["ema"]
            bullish_count += 1
            active.append("EMA Golden Stack (bullish)")
            details["ema"] = {
                "signal": "BULLISH",
                "reason": f"Preis {price:.2f} > EMA20 {p.ema20:.2f} > EMA50 {p.ema50:.2f} > EMA200 {p.ema200:.2f}",
                "strength": "stark"
            }
        elif bearish_stack:
            weighted_score -= WEIGHTS["ema"]
            bearish_count += 1
            active.append("EMA Death Stack (bearish)")
            details["ema"] = {
                "signal": "BEARISH",
                "reason": f"Preis {price:.2f} < EMA20 {p.ema20:.2f} < EMA50 {p.ema50:.2f} < EMA200 {p.ema200:.2f}",
                "strength": "stark"
            }
        elif price > p.ema50:
            # Teilweise bullish: Preis über mittelfristigem EMA
            weighted_score += WEIGHTS["ema"] // 2
            details["ema"] = {
                "signal": "SCHWACH BULLISH",
                "reason": f"Preis über EMA50, aber kein vollständiger Stack",
                "strength": "schwach"
            }
        elif price < p.ema50:
            weighted_score -= WEIGHTS["ema"] // 2
            details["ema"] = {
                "signal": "SCHWACH BEARISH",
                "reason": f"Preis unter EMA50, aber kein vollständiger Stack",
                "strength": "schwach"
            }
        else:
            details["ema"] = {"signal": "NEUTRAL", "reason": "Keine klare EMA-Ausrichtung"}
    else:
        details["ema"] = {"signal": "KEIN WERT", "reason": "EMA20/50/200 nicht übermittelt"}

    # ──────────────────────────────────────────────────────────────────────────
    # 2. MACD (Gewicht: 20%)
    # Logik: MACD-Linie über Signal-Linie = bullisches Momentum
    #        Histogram zeigt Stärke des Crossovers
    # ──────────────────────────────────────────────────────────────────────────
    if p.macd is not None and p.macd_signal is not None:
        total_weight += WEIGHTS["macd"]
        histogram = p.macd - p.macd_signal

        if histogram > 0:
            # Stärke skalieren: großes Histogram = stärkeres Signal
            weight_adj = WEIGHTS["macd"] if abs(histogram) > 0.001 * p.close else WEIGHTS["macd"] // 2
            weighted_score += weight_adj
            bullish_count += 1
            active.append("MACD über Signal-Linie")
            details["macd"] = {
                "signal": "BULLISH",
                "histogram": round(histogram, 6),
                "reason": f"MACD {p.macd:.4f} > Signal {p.macd_signal:.4f} — bullishes Momentum"
            }
        elif histogram < 0:
            weight_adj = WEIGHTS["macd"] if abs(histogram) > 0.001 * p.close else WEIGHTS["macd"] // 2
            weighted_score -= weight_adj
            bearish_count += 1
            active.append("MACD unter Signal-Linie")
            details["macd"] = {
                "signal": "BEARISH",
                "histogram": round(histogram, 6),
                "reason": f"MACD {p.macd:.4f} < Signal {p.macd_signal:.4f} — bearishes Momentum"
            }
        else:
            details["macd"] = {"signal": "NEUTRAL", "reason": "MACD = Signal-Linie"}
    else:
        details["macd"] = {"signal": "KEIN WERT", "reason": "MACD nicht übermittelt"}

    # ──────────────────────────────────────────────────────────────────────────
    # 3. RSI — Relative Strength Index (Gewicht: 15%)
    # Logik: RSI < 35 = überverkauft → Kaufgelegenheit
    #        RSI > 65 = überkauft → Verkaufsgelegenheit
    #        Klassische Grenzen: 30/70. Wir nutzen 35/65 für frühzeitigere Signale.
    # ──────────────────────────────────────────────────────────────────────────
    if p.rsi is not None:
        total_weight += WEIGHTS["rsi"]
        rsi = p.rsi

        if rsi < 30:
            weighted_score += WEIGHTS["rsi"]
            bullish_count += 1
            active.append(f"RSI extrem überverkauft ({rsi:.1f})")
            details["rsi"] = {"signal": "STARK BULLISH", "value": rsi, "reason": f"RSI {rsi:.1f} < 30 — extreme Überverkauftheit"}
        elif rsi < 40:
            weighted_score += WEIGHTS["rsi"] // 2
            details["rsi"] = {"signal": "BULLISH", "value": rsi, "reason": f"RSI {rsi:.1f} im überverkauften Bereich"}
        elif rsi > 70:
            weighted_score -= WEIGHTS["rsi"]
            bearish_count += 1
            active.append(f"RSI extrem überkauft ({rsi:.1f})")
            details["rsi"] = {"signal": "STARK BEARISH", "value": rsi, "reason": f"RSI {rsi:.1f} > 70 — extreme Überkauftheit"}
        elif rsi > 60:
            weighted_score -= WEIGHTS["rsi"] // 2
            details["rsi"] = {"signal": "BEARISH", "value": rsi, "reason": f"RSI {rsi:.1f} im überkauften Bereich"}
        else:
            details["rsi"] = {"signal": "NEUTRAL", "value": rsi, "reason": f"RSI {rsi:.1f} im neutralen Bereich (40–60)"}
    else:
        details["rsi"] = {"signal": "KEIN WERT", "reason": "RSI nicht übermittelt"}

    # ──────────────────────────────────────────────────────────────────────────
    # 4. BOLLINGER BANDS (Gewicht: 15%)
    # Logik: Preis < unteres Band → überverkauft, Rückkehr zur Mitte wahrscheinlich
    #        Preis > oberes Band → überkauft
    #        BB-Weite (Squeeze) zeigt bevorstehende Volatilität
    # ──────────────────────────────────────────────────────────────────────────
    if p.bb_upper and p.bb_lower and p.bb_basis:
        total_weight += WEIGHTS["bollinger"]
        price    = p.close
        bb_width = (p.bb_upper - p.bb_lower) / p.bb_basis  # Relative Bandbreite
        position = (price - p.bb_lower) / (p.bb_upper - p.bb_lower)  # 0=unten, 1=oben

        if price < p.bb_lower:
            weighted_score += WEIGHTS["bollinger"]
            bullish_count += 1
            active.append("Preis unter unterem Bollinger Band")
            details["bollinger"] = {
                "signal": "BULLISH", "bb_width": round(bb_width, 4),
                "position_pct": round(position * 100, 1),
                "reason": f"Preis {price:.2f} unter BB-Unterkante {p.bb_lower:.2f} — Mean-Reversion wahrscheinlich"
            }
        elif price > p.bb_upper:
            weighted_score -= WEIGHTS["bollinger"]
            bearish_count += 1
            active.append("Preis über oberem Bollinger Band")
            details["bollinger"] = {
                "signal": "BEARISH", "bb_width": round(bb_width, 4),
                "position_pct": round(position * 100, 1),
                "reason": f"Preis {price:.2f} über BB-Oberkante {p.bb_upper:.2f} — Rücksetzer wahrscheinlich"
            }
        elif bb_width < 0.02:
            # Squeeze: Bänder sehr eng → explosiver Move steht bevor
            details["bollinger"] = {
                "signal": "SQUEEZE",
                "bb_width": round(bb_width, 4),
                "reason": "Bollinger Squeeze — starker Move steht bevor (Richtung unklar)"
            }
        else:
            details["bollinger"] = {
                "signal": "NEUTRAL",
                "bb_width": round(bb_width, 4),
                "position_pct": round(position * 100, 1),
                "reason": "Preis innerhalb der Bänder"
            }
    else:
        details["bollinger"] = {"signal": "KEIN WERT", "reason": "Bollinger Bands nicht übermittelt"}

    # ──────────────────────────────────────────────────────────────────────────
    # 5. OBV — On-Balance Volume (Gewicht: 10%)
    # Logik: OBV steigt = Kaufdruck (Volumen fließt rein)
    #        OBV über seinem EMA = bestätigt Aufwärtstrend
    #        Divergenz: Preis steigt, OBV fällt → Warnsignal
    # ──────────────────────────────────────────────────────────────────────────
    if p.obv is not None and p.obv_ema is not None:
        total_weight += WEIGHTS["obv"]

        if p.obv > p.obv_ema:
            weighted_score += WEIGHTS["obv"]
            bullish_count += 1
            active.append("OBV über OBV-EMA (Kaufdruck)")
            details["obv"] = {
                "signal": "BULLISH",
                "obv": round(p.obv),
                "obv_ema": round(p.obv_ema),
                "reason": "OBV über EMA — Netto-Kaufdruck bestätigt Aufwärtstrend"
            }
        else:
            weighted_score -= WEIGHTS["obv"]
            bearish_count += 1
            active.append("OBV unter OBV-EMA (Verkaufsdruck)")
            details["obv"] = {
                "signal": "BEARISH",
                "obv": round(p.obv),
                "obv_ema": round(p.obv_ema),
                "reason": "OBV unter EMA — Netto-Verkaufsdruck"
            }
    else:
        details["obv"] = {"signal": "KEIN WERT", "reason": "OBV nicht übermittelt"}

    # ──────────────────────────────────────────────────────────────────────────
    # 6. PIVOT POINTS (Gewicht: 10%)
    # Logik: Preis über R1 (Resistance 1) = Ausbruch nach oben
    #        Preis unter S1 (Support 1) = Ausbruch nach unten
    #        Pivot Points basieren auf High/Low/Close der Vorperiode
    # ──────────────────────────────────────────────────────────────────────────
    if p.pivot_r1 and p.pivot_s1:
        total_weight += WEIGHTS["pivot"]
        price = p.close

        if price > p.pivot_r1:
            weighted_score += WEIGHTS["pivot"]
            bullish_count += 1
            active.append(f"Preis über R1 Pivot ({p.pivot_r1:.2f})")
            details["pivot"] = {
                "signal": "BULLISH",
                "r1": p.pivot_r1, "s1": p.pivot_s1, "price": price,
                "reason": f"Preis {price:.2f} über Resistance R1 {p.pivot_r1:.2f} — Ausbruch bestätigt"
            }
        elif price < p.pivot_s1:
            weighted_score -= WEIGHTS["pivot"]
            bearish_count += 1
            active.append(f"Preis unter S1 Pivot ({p.pivot_s1:.2f})")
            details["pivot"] = {
                "signal": "BEARISH",
                "r1": p.pivot_r1, "s1": p.pivot_s1, "price": price,
                "reason": f"Preis {price:.2f} unter Support S1 {p.pivot_s1:.2f} — Unterstützung gebrochen"
            }
        else:
            details["pivot"] = {
                "signal": "NEUTRAL",
                "r1": p.pivot_r1, "s1": p.pivot_s1, "price": price,
                "reason": f"Preis zwischen S1 {p.pivot_s1:.2f} und R1 {p.pivot_r1:.2f}"
            }
    else:
        details["pivot"] = {"signal": "KEIN WERT", "reason": "Pivot Points nicht übermittelt"}

    # ──────────────────────────────────────────────────────────────────────────
    # 7. FEAR & GREED INDEX (Gewicht: 5%)
    # Logik: KONTRAINDIKATOR — extremes Sentiment kehrt sich um
    #        < 20 = extreme Angst → Kaufen (alle haben Panik)
    #        > 80 = extreme Gier  → Verkaufen (alle sind euphorisch)
    #        Nur für Krypto-Märkte sinnvoll
    # ──────────────────────────────────────────────────────────────────────────
    if p.fear_greed is not None:
        total_weight += WEIGHTS["fear_greed"]
        fg = p.fear_greed

        if fg < 20:
            weighted_score += WEIGHTS["fear_greed"]
            bullish_count += 1
            active.append(f"Extreme Angst — Kontraindikator bullish ({fg:.0f})")
            details["fear_greed"] = {
                "signal": "BULLISH (Kontraindikator)",
                "value": fg,
                "reason": f"Fear & Greed {fg:.0f} — extreme Angst, historisch guter Einstieg"
            }
        elif fg > 80:
            weighted_score -= WEIGHTS["fear_greed"]
            bearish_count += 1
            active.append(f"Extreme Gier — Kontraindikator bearish ({fg:.0f})")
            details["fear_greed"] = {
                "signal": "BEARISH (Kontraindikator)",
                "value": fg,
                "reason": f"Fear & Greed {fg:.0f} — extreme Gier, historisch schlechter Zeitpunkt"
            }
        else:
            details["fear_greed"] = {
                "signal": "NEUTRAL",
                "value": fg,
                "reason": f"Fear & Greed {fg:.0f} — kein Extremwert"
            }
    else:
        details["fear_greed"] = {"signal": "KEIN WERT", "reason": "Fear & Greed nicht übermittelt"}

    # ──────────────────────────────────────────────────────────────────────────
    # GESAMTSIGNAL berechnen
    # Gewichteter Score normalisiert auf 0–100
    # ──────────────────────────────────────────────────────────────────────────
    if total_weight == 0:
        return SignalResult(
            signal="NEUTRAL", score=0, max_score=0,
            confidence=0, active_signals=["Keine Indikatoren empfangen"],
            details=details
        )

    # Normalisierung: weighted_score liegt zwischen -total_weight und +total_weight
    # → auf 0–100 skalieren
    confidence = int(((weighted_score / total_weight) + 1) / 2 * 100)
    confidence = max(0, min(100, confidence))

    if confidence >= 65:
        signal = "KAUFEN"
        score  = bullish_count
    elif confidence <= 35:
        signal = "VERKAUFEN"
        score  = bearish_count
    else:
        signal = "NEUTRAL"
        score  = max(bullish_count, bearish_count)

    return SignalResult(
        signal=signal,
        score=score,
        max_score=len([d for d in details.values() if d.get("signal") != "KEIN WERT"]),
        confidence=confidence,
        active_signals=active,
        details=details
    )

