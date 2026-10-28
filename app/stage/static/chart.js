/* TradingView-styled chart engine: lightweight-charts v5 (ESM) + TradingView's official plugin primitives
   (trend line, rectangle, volume profile) + a canvas overlay for everything else a chartist draws:
   Fibonacci retracement / extension / fan, parallel and regression channels, pitchfork, long/short position,
   measure ruler, pattern outlines with forming / confirmed / invalidated states, session shading, key levels,
   anchored VWAP, built-in studies (EMA, SMA, Bollinger, VWAP, RSI, MACD, ATR in panes), alerts, notes.
   Every drawing may carry an id: redrawing with the same id replaces it (no duplicates). All times are unix seconds (UTC). */
import { createChart, CandlestickSeries, HistogramSeries, LineSeries, createSeriesMarkers, createTextWatermark, LineStyle, CrosshairMode, PriceScaleMode } from "lightweight-charts";
import { TrendLine } from "lwc-plugins/trend-line.js";
import { Rectangle, RectangleDrawingTool } from "lwc-plugins/rectangle-drawing-tool.js";
import { VolumeProfile } from "lwc-plugins/volume-profile.js";

// TradingView's dark palette (the one every chart on TikTok looks like): #131722 canvas, #1e222d grid, #2a2e39 lines, #d1d4dc text
const TV = { bg: "#131722", grid: "#1e222d", border: "#2a2e39", panel: "#2a2e39", text: "#d1d4dc", muted: "#787b86", blue: "#2962ff", up: "#089981", down: "#f23645",
  chip: "rgba(19,23,34,.92)", label: "#d1d4dc" };
const FONT = '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
const DRAW_MS = 420;
const TF_S = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800 };
const SESSIONS = { asia: [0, 8], london: [7, 16], newyork: [12, 21] };     // UTC hours, forex convention
const STATE_GREY = "#9598a1";

function hash(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
const fmtP = (p) => (p >= 1000 ? p.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : p >= 10 ? p.toFixed(2) : p.toFixed(4));
function rgba(col, a) {
  // "#rrggbb" or "rgba(r,g,b,x)" -> rgba with the given alpha
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(col || "");
  if (m) return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})`;
  const r = /rgba?\(([^)]+)\)/.exec(col || "");
  if (r) { const p = r[1].split(",").map((x) => x.trim()); return `rgba(${p[0]},${p[1]},${p[2]},${a})`; }
  return col;
}
function ema(values, n) { const out = new Array(values.length).fill(null); if (values.length < n) return out; const k = 2 / (n + 1); let e = values.slice(0, n).reduce((a, b) => a + b, 0) / n; out[n - 1] = e; for (let i = n; i < values.length; i++) { e = values[i] * k + e * (1 - k); out[i] = e; } return out; }
function sma(values, n) { const out = new Array(values.length).fill(null); let s = 0; for (let i = 0; i < values.length; i++) { s += values[i]; if (i >= n) s -= values[i - n]; if (i >= n - 1) out[i] = s / n; } return out; }
function stdev(values, n) { const out = new Array(values.length).fill(null); for (let i = n - 1; i < values.length; i++) { const seg = values.slice(i - n + 1, i + 1); const m = seg.reduce((a, b) => a + b, 0) / n; out[i] = Math.sqrt(seg.reduce((a, b) => a + (b - m) * (b - m), 0) / n); } return out; }
function rsi(values, n) {
  const out = new Array(values.length).fill(null); if (values.length <= n) return out;
  let ag = 0, al = 0; for (let i = 1; i <= n; i++) { const d = values[i] - values[i - 1]; if (d > 0) ag += d; else al -= d; } ag /= n; al /= n;
  out[n] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
  for (let i = n + 1; i < values.length; i++) { const d = values[i] - values[i - 1]; ag = (ag * (n - 1) + Math.max(0, d)) / n; al = (al * (n - 1) + Math.max(0, -d)) / n; out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al); }
  return out;
}
function atr(cs, n) { const tr = cs.map((c, i) => i === 0 ? c.high - c.low : Math.max(c.high - c.low, Math.abs(c.high - cs[i - 1].close), Math.abs(c.low - cs[i - 1].close))); return ema(tr, n); }

export class ChartEngine {
  constructor(container, overlay, onReplayDone) {
    this.container = container;
    this.overlay = overlay;
    this.ctx = overlay.getContext("2d");
    this.onReplayDone = onReplayDone || (() => {});
    this.chart = createChart(container, {
      layout: { background: { type: "solid", color: TV.bg }, textColor: TV.text, fontSize: 18, fontFamily: FONT, attributionLogo: true,
                panes: { separatorColor: TV.border, separatorHoverColor: "rgba(41,98,255,0.2)", enableResize: true } },
      grid: { vertLines: { color: TV.grid }, horzLines: { color: TV.grid } },
      // candles fill the pane like TradingView: small margins, volume in the bottom fifth, no overlay allowed to stretch the scale
      rightPriceScale: { borderColor: TV.border, scaleMargins: { top: 0.06, bottom: 0.2 }, textColor: TV.text, entireTextOnly: true },
      timeScale: { borderColor: TV.border, timeVisible: true, secondsVisible: false, rightOffset: 8, barSpacing: 13, minBarSpacing: 0.5 },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#9598a1", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#4c525e" },
                   horzLine: { color: "#9598a1", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#4c525e" } },
      // full TradingView interaction: wheel zoom, drag to pan, drag an axis to stretch it, double-click an axis to reset
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: { time: true, price: true }, mouseWheel: true, pinch: true, axisDoubleClickReset: { time: true, price: true } },
      kineticScroll: { mouse: true, touch: true },
    });
    // operator interaction lock: while someone is using the chart, automatic fit/scroll/zoom stay out of the way
    this.userUntil = 0;
    const touch = () => { this.userUntil = Date.now() + 120000; };
    container.addEventListener("pointerdown", touch);
    container.addEventListener("wheel", touch, { passive: true });
    container.addEventListener("dblclick", () => { this.userUntil = 0; if (this.tool === "Brush" && this._toolPts.length >= 2) this._finishBrush(); });
    this.tool = "Cursor";
    this.magnet = false;        // snap operator clicks to the nearest O/H/L/C of the bar under the cursor
    this.hidden = false;        // hide all drawings (eye button)
    this.locked = false;        // operator drawings survive the lesson's clear()
    this.userItems = [];        // hand-drawn price lines / primitives (cleared by the Remove tool)
    this._toolPts = [];
    this.rectTool = null;
    this.chart.subscribeClick((param) => this._toolClick(param));
    // infinite history: when the left edge comes into view, ask for older bars (like TradingView)
    this.onNeedHistory = null;      // (firstTime) => void, set by the stage
    this.onAlert = null;            // ({id, label, price, direction}) => void
    this.historyDone = false;
    this.loadingMore = 0;
    this.chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (!r || this.historyDone || this.replayTimer || !this.candles.length) return;
      if (r.from < 40 && Date.now() > this.loadingMore && this.onNeedHistory) {
        this.loadingMore = Date.now() + 8000;
        this.onNeedHistory(this.candles[0].time);
      }
    });
    // the candle itself is TradingView's own renderer (lightweight-charts is their library): body with a 1 px border in the
    // same colour, 1 px wick, 1 px gap between bars, exactly as on tradingview.com in the default dark theme
    this.series = this.chart.addSeries(CandlestickSeries, {
      upColor: TV.up, downColor: TV.down, borderVisible: true, borderUpColor: TV.up, borderDownColor: TV.down, wickVisible: true, wickUpColor: TV.up, wickDownColor: TV.down,
      priceLineColor: TV.blue, priceLineStyle: LineStyle.Dashed, priceLineWidth: 1, lastValueVisible: true,
    });
    this.volume = this.chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol", color: "#26a69a", lastValueVisible: false, priceLineVisible: false });
    this.chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    this.markers = createSeriesMarkers(this.series, []);
    this.markerList = [];
    this.priceLines = [];     // {obj, id, user}
    this.primitives = [];     // {obj, id, user}  TradingView plugin primitives attached to the series
    this.drawings = [];       // overlay items: {kind, ..., born, id, user}
    this.indicators = [];     // {obj, id, user, pane}  line/histogram series (overlays and pane studies)
    this.candles = [];
    this.replayTimer = null;
    this.tf = "15m";
    this.onLegend = null;     // (candle, prevClose) => void
    this.symbol = "";
    this.watermark = createTextWatermark(this.chart.panes()[0], { horzAlign: "center", vertAlign: "center", lines: [] });
    this._pingUntil = 0;
    this._flashUntil = 0;
    this.resize();
    window.addEventListener("resize", () => this.resize());
    const draw = () => { this.drawOverlay(); requestAnimationFrame(draw); };
    requestAnimationFrame(draw);
    this._hoverT = 0;
  }

  resize() {
    const w = this.container.offsetWidth, h = this.container.offsetHeight;
    if (w < 50 || h < 50) return;      // hidden/minimised: a 0x0 resize would blank the canvases
    this.chart.resize(w, h);
    this.overlay.width = w; this.overlay.height = h;
  }

  _stopReplay() { if (this.replayTimer) { clearInterval(this.replayTimer); this.replayTimer = null; } }
  _vol(c) { return { time: c.time, value: c.volume || 0, color: c.close >= c.open ? "rgba(8,153,129,.5)" : "rgba(242,54,69,.5)" }; }
  _legend() { const n = this.candles.length; if (n && this.onLegend) this.onLegend(this.candles[n - 1], n > 1 ? this.candles[n - 2].close : this.candles[n - 1].open); }
  _idx(t) { const cs = this.candles; let lo = 0, hi = cs.length - 1; if (!cs.length) return -1; if (t <= cs[0].time) return 0; if (t >= cs[hi].time) return hi; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (cs[m].time <= t) lo = m; else hi = m; } return lo; }
  _atr14() { const cs = this.candles; if (cs.length < 16) return cs.length ? (cs[cs.length - 1].high - cs[cs.length - 1].low) : 0; const a = atr(cs, 14); return a[a.length - 1] || 0; }

  setWatermark(symbol, tf, source) {
    this.symbol = symbol || this.symbol;
    const tfLabel = ({ "1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D", "1w": "W" })[tf] || tf;
    this.watermark.applyOptions({ lines: [
      { text: (symbol || "").replace("/", ""), color: "rgba(255,255,255,0.05)", fontSize: 84, fontStyle: "bold", fontFamily: FONT },
      { text: `${tfLabel} · ${source || ""}`, color: "rgba(255,255,255,0.05)", fontSize: 30, fontFamily: FONT },
    ] });
  }

  ping(time, price) {
    // a brief crosshair on a freshly drawn element, like a cursor pointing at it
    try { this.chart.setCrosshairPosition(price, time, this.series); this._pingUntil = performance.now() + 1600; } catch (e) { /* off-range */ }
  }

  // The lesson view: the analysis window (last ~90 bars) fills the chart with the live candle at the right edge.
  _viewRecent(total) {
    const n = total != null ? total : this.candles.length;
    if (!n) return;
    const show = Math.min(n, (TF_S[this.tf] || 0) <= 60 ? 100 : 72);     // fewer bars in view = TradingView-sized candles on a 1080 px stage
    this.chart.timeScale().setVisibleLogicalRange({ from: n - show - 0.5, to: n + 7 });
  }

  // Clean candles: finite OHLC, ascending unique times. lightweight-charts throws on unsorted or duplicate
  // times and the series is left empty; that is how a chart "disappears". Never let bad data reach it.
  _clean(arr) {
    const ok = (arr || []).filter((c) => c && Number.isFinite(c.time) && [c.open, c.high, c.low, c.close].every(Number.isFinite));
    ok.sort((a, b) => a.time - b.time);
    const out = [];
    for (const c of ok) { if (out.length && out[out.length - 1].time === c.time) out[out.length - 1] = c; else out.push(c); }
    return out;
  }

  load(msg) {
    const candles = this._clean(msg.candles);
    if (!candles.length) { console.warn("load without candles ignored"); return; }   // keep what is on screen
    this._stopReplay();
    this.clear();
    this.userUntil = 0;
    this.historyDone = false; this.loadingMore = 0;
    this.chart.priceScale("right").applyOptions({ autoScale: true });
    this.candles = candles;
    this.tf = msg.tf || this.tf;
    const vp = this._volumeProfile();
    if (!msg.replay || this.candles.length < 5) {
      this.series.setData(this.candles);
      this.volume.setData(this.candles.map((c) => this._vol(c)));
      this._viewRecent();
      if (vp) this._attach(vp);
      this._legend();
      this.onReplayDone();
      return;
    }
    const warm = Math.max(3, this.candles.length - 60);   // draw in only the last 60 bars; history is just there
    let i = warm;
    this.series.setData(this.candles.slice(0, warm));
    this.volume.setData(this.candles.slice(0, warm).map((c) => this._vol(c)));
    this._viewRecent(this.candles.length);     // the view already frames the bars that are about to draw in
    const pace = Math.max(20, msg.pace_ms || 45);
    this.replayTimer = setInterval(() => {
      try {
        if (i >= this.candles.length) { this._stopReplay(); if (this._autoOk()) this._viewRecent(); if (vp) this._attach(vp); this._legend(); this.onReplayDone(); return; }
        const c = this.candles[i++];
        this.series.update(c); this.volume.update(this._vol(c));
      } catch (err) {    // never leave a half-drawn chart: finish with the full data set
        console.error("replay step failed", err);
        this._stopReplay();
        this.series.setData(this.candles); this.volume.setData(this.candles.map((x) => this._vol(x)));
        if (vp) this._attach(vp); this._legend(); this.onReplayDone();
      }
    }, pace);
  }

  prepend(msg) {
    // older bars arrived: merge in front, keep the viewer's exact view (logical indices shift by the count added)
    this.loadingMore = 0;
    const older = (msg.candles || []).filter((c) => this.candles.length && c.time < this.candles[0].time);
    if (!older.length) { this.historyDone = true; return; }
    const ts = this.chart.timeScale();
    const r = ts.getVisibleLogicalRange();
    const merged = this._clean(older.concat(this.candles));
    const added = merged.length - this.candles.length;
    this.candles = merged;
    try { this.series.setData(this.candles); this.volume.setData(this.candles.map((c) => this._vol(c))); }
    catch (err) { console.error("prepend failed", err); this.historyDone = true; return; }
    if (r && added > 0) ts.setVisibleLogicalRange({ from: r.from + added, to: r.to + added });
    if (msg.end) this.historyDone = true;
    this._recomputeStudies();
  }

  update(candle) {
    if (!candle || !Number.isFinite(candle.time) || ![candle.open, candle.high, candle.low, candle.close].every(Number.isFinite)) return;
    const n = this.candles.length;
    if (n && candle.time < this.candles[n - 1].time) return;        // older than the last bar: the library would throw
    const prevClose = n ? this.candles[n - 1].close : candle.close;
    if (this.replayTimer) {                                           // during the draw-in the replay will reach it
      if (n && this.candles[n - 1].time === candle.time) this.candles[n - 1] = candle; else this.candles.push(candle);
      return;
    }
    try { this.series.update(candle); this.volume.update(this._vol(candle)); }
    catch (err) { console.error("update failed", err); return; }
    const newBar = !(n && this.candles[n - 1].time === candle.time);
    if (!newBar) this.candles[n - 1] = candle; else this.candles.push(candle);
    this._legend();
    this._checkAlerts(prevClose, candle.close);
    if (newBar) this._recomputeStudies(); else this._updateStudiesLast();
  }

  _attach(p, id, user) { this.series.attachPrimitive(p); this.primitives.push({ obj: p, id: id || null, user: !!user }); }
  _autoOk() { return Date.now() > this.userUntil; }

  // ---- ids: the same id replaces the previous object, so updates never pile up duplicates ----
  _dropId(id) {
    if (!id) return;
    this.drawings = this.drawings.filter((d) => d.id !== id);
    for (const pl of this.priceLines.filter((x) => x.id === id)) { try { this.series.removePriceLine(pl.obj); } catch (e) { /* gone */ } }
    this.priceLines = this.priceLines.filter((x) => x.id !== id);
    for (const pr of this.primitives.filter((x) => x.id === id)) { try { this.series.detachPrimitive(pr.obj); } catch (e) { /* gone */ } }
    this.primitives = this.primitives.filter((x) => x.id !== id);
    for (const s of this.indicators.filter((x) => x.id === id)) { try { this.chart.removeSeries(s.obj); } catch (e) { /* gone */ } }
    this.indicators = this.indicators.filter((x) => x.id !== id);
    this.markerList = this.markerList.filter((m) => m.id !== id);
    this.markers.setMarkers(this.markerList);
  }
  remove(msg) {
    if (!msg || !msg.id) return;
    if (msg.state) {      // restyle instead of removing: the honest record stays on the chart
      for (const d of this.drawings) if (d.id === msg.id) d.state = msg.state;
      for (const pl of this.priceLines) if (pl.id === msg.id) { try { pl.obj.applyOptions({ color: msg.state === "invalidated" ? STATE_GREY : pl.color, lineStyle: msg.state === "forming" ? LineStyle.Dashed : LineStyle.Solid, title: (msg.state === "invalidated" ? "✕ " : "") + (pl.title || "") }); } catch (e) { /* gone */ } }
      return;
    }
    this._dropId(msg.id);
  }
  _stateOf(d) {
    // forming = dashed, confirmed = solid, invalidated = grey + cross prefix on the label
    const st = d.state || null;
    return { dashed: st === "forming" ? true : st === "confirmed" ? false : null, color: st === "invalidated" ? STATE_GREY : null, prefix: st === "invalidated" ? "✕ " : st === "forming" ? "… " : "" };
  }

  // ---- operator interaction (the TradingView chrome is live, not decoration) ----
  setRange(key) {
    const cs = this.candles; if (!cs.length) return;
    const ts = this.chart.timeScale(); this.userUntil = Date.now() + 120000;
    const spans = { "1D": 86400, "5D": 5 * 86400, "1M": 30 * 86400, "3M": 90 * 86400, "6M": 180 * 86400, "1Y": 365 * 86400, "5Y": 5 * 365 * 86400 };
    const last = cs[cs.length - 1].time;
    let from = null;
    if (key === "YTD") from = Date.UTC(new Date(last * 1000).getUTCFullYear(), 0, 1) / 1000;
    else if (spans[key]) from = last - spans[key];
    if (from == null || from <= cs[0].time) { ts.fitContent(); return; }
    try { ts.setVisibleRange({ from, to: last }); } catch (e) { ts.fitContent(); }
  }
  setScaleMode(key) {
    const ps = this.chart.priceScale("right"); const cur = ps.options();
    if (key === "auto") ps.applyOptions({ autoScale: true });
    else if (key === "log") ps.applyOptions({ mode: cur.mode === PriceScaleMode.Logarithmic ? PriceScaleMode.Normal : PriceScaleMode.Logarithmic });
    else if (key === "%") ps.applyOptions({ mode: cur.mode === PriceScaleMode.Percentage ? PriceScaleMode.Normal : PriceScaleMode.Percentage });
    const o = ps.options();
    return { auto: !!o.autoScale, log: o.mode === PriceScaleMode.Logarithmic, "%": o.mode === PriceScaleMode.Percentage };
  }
  // toggles return their new state so the toolbar can light up
  toggleMagnet() { this.magnet = !this.magnet; return this.magnet; }
  toggleLock() { this.locked = !this.locked; return this.locked; }
  toggleHidden() {
    this.hidden = !this.hidden;
    for (const pl of this.priceLines) { try { pl.obj.applyOptions({ lineVisible: !this.hidden, axisLabelVisible: !this.hidden && !!pl.axis }); } catch (e) { /* gone */ } }
    for (const s of this.indicators) { try { s.obj.applyOptions({ visible: !this.hidden }); } catch (e) { /* gone */ } }
    for (const pr of this.primitives) { try { if (this.hidden) this.series.detachPrimitive(pr.obj); else this.series.attachPrimitive(pr.obj); } catch (e) { /* gone */ } }
    this.markers.setMarkers(this.hidden ? [] : this.markerList);
    return this.hidden;
  }
  setTool(name) {
    if (this.rectTool && this.rectTool.isDrawing()) this.rectTool.stopDrawing();
    this._toolPts = [];
    if (name === "Remove") { this.clearUserItems(); name = "Cursor"; }
    this.tool = name;
    if (name === "Rectangle") {
      if (!this.rectTool) this.rectTool = new RectangleDrawingTool(this.chart, this.series, undefined,
        { fillColor: "rgba(41,98,255,0.22)", previewFillColor: "rgba(41,98,255,0.12)", labelColor: TV.blue, labelTextColor: "#fff", showLabels: true, priceLabelFormatter: (p) => p.toFixed(2), timeLabelFormatter: (t) => new Date((typeof t === "number" ? t : 0) * 1000).toISOString().slice(5, 16).replace("T", " ") });
      this.rectTool.startDrawing();
    }
    this.userUntil = Date.now() + 120000;
    return this.tool;
  }
  clearUserItems() {
    for (const it of this.userItems) { try { it.kind === "pl" ? this.series.removePriceLine(it.obj) : it.kind === "series" ? this.chart.removeSeries(it.obj) : this.series.detachPrimitive(it.obj); } catch (e) { /* gone */ } }
    this.userItems = [];
    this.priceLines = this.priceLines.filter((x) => !x.user);
    this.primitives = this.primitives.filter((x) => !x.user);
    this.indicators = this.indicators.filter((x) => !x.user);
    this.drawings = this.drawings.filter((d) => !d.user);
    if (this.rectTool) { try { this.rectTool.remove(); } catch (e) { /* gone */ } this.rectTool = null; }
  }
  _snap(time, price, y) {
    // magnet: the nearest open/high/low/close of the bar under the cursor, when it is within 14 px
    if (!this.magnet) return price;
    const c = this.candles[this._idx(time)]; if (!c) return price;
    let best = price, bd = 14;
    for (const v of [c.open, c.high, c.low, c.close]) { const yy = this.series.priceToCoordinate(v); if (yy == null) continue; const d = Math.abs(yy - y); if (d < bd) { bd = d; best = v; } }
    return best;
  }
  _finishBrush() {
    const pts = this._toolPts; this._toolPts = [];
    if (pts.length >= 2) this.path({ points: pts, color: TV.blue, width: 2, user: true });
    this.tool = "Cursor"; this.onToolDone && this.onToolDone();
  }
  _toolClick(param) {
    if (!param || !param.point || this.tool === "Cursor" || this.tool === "Rectangle") return;
    let price = this.series.coordinateToPrice(param.point.y); if (price == null) return;
    const time = param.time || this.chart.timeScale().coordinateToTime(param.point.x); if (time == null) return;
    price = this._snap(time, price, param.point.y);
    const done = () => { this.tool = "Cursor"; this._toolPts = []; this.onToolDone && this.onToolDone(); };
    const need = { "Trend line": 2, Measure: 2, Fib: 2, Ray: 2, Arrow: 2, Channel: 3, Pitchfork: 3, "Fib extension": 3, "Vol profile": 2, Regression: 2 }[this.tool];
    if (this.tool === "Horizontal line") {
      const pl = this.series.createPriceLine({ price, color: TV.blue, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "" });
      this.userItems.push({ kind: "pl", obj: pl }); this.priceLines.push({ obj: pl, id: null, user: true, axis: true }); done();
    } else if (this.tool === "Vertical line") { this.vline({ time, color: TV.blue, style: "solid", user: true }); done(); }
    else if (this.tool === "Text") {
      // click on an existing note edits it; otherwise a new note is started at the click point
      const hit = this.drawings.find((d) => d.kind === "note" && d.user && d._box && param.point.x >= d._box[0] && param.point.x <= d._box[0] + d._box[2] && param.point.y >= d._box[1] && param.point.y <= d._box[1] + d._box[3]);
      if (this.onTextEdit) this.onTextEdit({ time: hit ? hit.time : time, price: hit ? hit.price : price, x: param.point.x, y: param.point.y, existing: hit || null });
      done();
    }
    else if (this.tool === "Alert") { this.alert({ price, label: "alert", user: true }); done(); }
    else if (this.tool === "Anchored VWAP") { this.avwap({ anchor: time, label: "AVWAP", user: true }); done(); }
    else if (this.tool === "Long position" || this.tool === "Short position") {
      const long = this.tool === "Long position", r = Math.max(this._atr14() * 1.5, price * 0.002);
      this.position({ side: long ? "long" : "short", time, entry: price, stop: long ? price - r : price + r, target: long ? price + 2 * r : price - 2 * r, user: true }); done();
    } else if (this.tool === "Brush") {
      this._toolPts.push({ time, price });
      const f = this._toolPts[0]; if (this._toolPts.length > 2 && Math.abs(f.time - time) < 1 && Math.abs(f.price - price) < 1e-9) this._finishBrush();
    } else if (need) {
      this._toolPts.push({ time, price });
      if (this._toolPts.length < need) return;
      const [a, b, c] = this._toolPts;
      if (this.tool === "Trend line") this.trendline({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, color: TV.blue, user: true });
      else if (this.tool === "Ray") this.trendline({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, color: TV.blue, extend: "right", user: true });
      else if (this.tool === "Measure") this.measure({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, user: true });
      else if (this.tool === "Fib") this.fib({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, user: true });
      else if (this.tool === "Arrow") this.arrow({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, color: TV.blue, user: true });
      else if (this.tool === "Channel") this.channel({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, t3: c.time, p3: c.price, color: TV.blue, user: true });
      else if (this.tool === "Pitchfork") this.pitchfork({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, t3: c.time, p3: c.price, user: true });
      else if (this.tool === "Fib extension") this.fibExt({ t1: a.time, p1: a.price, t2: b.time, p2: b.price, t3: c.time, p3: c.price, user: true });
      else if (this.tool === "Vol profile") this.vprofile({ start: Math.min(a.time, b.time), end: Math.max(a.time, b.time), user: true });
      else if (this.tool === "Regression") this.regression({ start: Math.min(a.time, b.time), end: Math.max(a.time, b.time), user: true });
      done();
    }
  }

  _volumeProfile() {
    // TradingView-style volume profile over the loaded window (right side of the chart)
    const cs = this.candles.slice(-90); if (cs.length < 20) return null;   // profile of the analysis window, not the whole history
    const prof = this._profile(cs, 24); if (!prof) return null;
    return new VolumeProfile(this.chart, this.series, { time: cs[Math.max(0, cs.length - 9)].time, profile: prof.profile, width: 8 });
  }
  _profile(cs, rows) {
    const lo = Math.min(...cs.map((c) => c.low)), hi = Math.max(...cs.map((c) => c.high)); if (hi <= lo) return null;
    const step = (hi - lo) / rows, bins = new Array(rows).fill(0);
    for (const c of cs) { const v = c.volume || 1; const a = Math.max(0, Math.floor((c.low - lo) / step)), b = Math.min(rows - 1, Math.floor((c.high - lo) / step)); for (let k = a; k <= b; k++) bins[k] += v / (b - a + 1); }
    const total = bins.reduce((x, y) => x + y, 0); let poc = 0; bins.forEach((v, k) => { if (v > bins[poc]) poc = k; });
    // value area: grow from the POC until 70% of the volume is inside
    let a = poc, b = poc, acc = bins[poc];
    while (acc < total * 0.7 && (a > 0 || b < rows - 1)) { const up = b < rows - 1 ? bins[b + 1] : -1, dn = a > 0 ? bins[a - 1] : -1; if (up >= dn) { b++; acc += up; } else { a--; acc += dn; } }
    return { profile: bins.map((vol, k) => ({ price: lo + step * (k + 0.5), vol })), poc: lo + step * (poc + 0.5), vah: lo + step * (b + 1), val: lo + step * a, lo, hi };
  }

  // ---- drawings the brain (or the operator) asks for ----
  marker(msg) {
    this._dropId(msg.id);
    if (typeof msg.time === "number") { const c = this.candles.find((k) => k.time === msg.time); if (c) this.ping(msg.time, msg.position === "aboveBar" ? c.high : c.low); }
    this.markerList.push({ time: msg.time, position: msg.position || "belowBar", shape: msg.shape || "arrowUp", color: msg.color || TV.blue, text: msg.text || "", size: 1, id: msg.id || null });
    this.markerList.sort((a, b) => a.time - b.time);
    if (!this.hidden) this.markers.setMarkers(this.markerList);
  }

  _priceLine(msg, price, title, color, style, axis) {
    const st = this._stateOf(msg);
    const ls = { solid: LineStyle.Solid, dotted: LineStyle.Dotted, dashed: LineStyle.Dashed }[style || "dashed"];
    const pl = this.series.createPriceLine({ price, color: st.color || color, lineWidth: 1, lineStyle: st.dashed === true ? LineStyle.Dashed : st.dashed === false ? LineStyle.Solid : ls, axisLabelVisible: !!axis && !this.hidden, lineVisible: !this.hidden, title: st.prefix + (title || "") });
    this.priceLines.push({ obj: pl, id: msg.id || null, user: !!msg.user, axis: !!axis, color, title });
    if (msg.user) this.userItems.push({ kind: "pl", obj: pl });
    return pl;
  }
  hline(msg) {
    this._dropId(msg.id);
    // axis labels only for the levels a trader keys on (invalidation, entry, stop, target); the rest keep their on-chart chip,
    // otherwise the price scale turns into a stack of overlapping tags
    const key = /invalidation|entry|stop|target/i.test(msg.label || "");
    this._priceLine(msg, msg.price, msg.label || "", msg.color || TV.blue, msg.style, key);
  }

  trendline(msg) {
    this._dropId(msg.id);
    const ext = msg.extend === true ? "right" : msg.extend || "none";
    const cs = this.candles, st = this._stateOf(msg);
    let p1 = { time: msg.t1, price: msg.p1 }, p2 = { time: msg.t2, price: msg.p2 };
    if (ext !== "none" && cs.length >= 2) {    // extend along the bar index axis to the right edge (and the left edge for 'both')
      const ia = this._idx(msg.t1), ib = this._idx(msg.t2);
      if (ib !== ia) {
        const k = (msg.p2 - msg.p1) / (ib - ia);
        p2 = { time: cs[cs.length - 1].time, price: msg.p1 + k * (cs.length - 1 - ia) };
        if (ext === "both") p1 = { time: cs[0].time, price: msg.p1 + k * (0 - ia) };
      }
    }
    const col = st.color || msg.color || TV.blue;
    const tl = new TrendLine(this.chart, this.series, p1, p2, { lineColor: col, width: 2, showLabels: !!msg.label, labelBackgroundColor: col, labelTextColor: "#fff" });
    this._attach(tl, msg.id, msg.user);
    if (msg.user) this.userItems.push({ kind: "prim", obj: tl });
    if (msg.label && (ext !== "none" || st.prefix)) this._add({ kind: "label", time: p2.time, price: p2.price, text: st.prefix + msg.label, color: col, dx: -40, id: msg.id ? msg.id + ":lbl" : null, user: msg.user });
    if (ext !== "none") this._add({ kind: "line", t1: p1.time, p1: p1.price, t2: p2.time, p2: p2.price, color: col, dashed: st.dashed === true, width: 2, toEdge: ext, id: msg.id ? msg.id + ":ext" : null, user: msg.user });
  }

  rect(msg) { this._dropId(msg.id); const st = this._stateOf(msg); const col = st.color ? rgba(STATE_GREY, 0.18) : (msg.color || "rgba(41,98,255,0.2)"); const r = new Rectangle({ time: msg.t1, price: msg.top }, { time: msg.t2, price: msg.bottom }, { fillColor: col, previewFillColor: col, labelColor: msg.color || TV.blue, labelTextColor: "#fff", showLabels: false }); this._attach(r, msg.id, msg.user); this._note(msg, msg.t1, msg.top); }
  zone(msg) {
    this._dropId(msg.id);
    const cs = this.candles; if (!cs.length) return;
    const st = this._stateOf(msg); const col = st.color ? rgba(STATE_GREY, 0.18) : (msg.color || "rgba(41,98,255,0.18)");
    this._attach(new Rectangle({ time: cs[0].time, price: msg.top }, { time: cs[cs.length - 1].time, price: msg.bottom }, { fillColor: col, previewFillColor: col, labelColor: TV.blue, labelTextColor: "#fff", showLabels: false }), msg.id, msg.user);
    this._note(msg, cs[0].time, msg.top, 10);
  }
  _note(msg, t, p, dx = 6) { const st = this._stateOf(msg); if (msg.label) this._add({ kind: "label", time: t, price: p, text: st.prefix + msg.label, color: st.color || msg.color || TV.blue, dx, id: msg.id ? msg.id + ":lbl" : null, user: msg.user }); }

  _add(item) { if (item.id) this.drawings = this.drawings.filter((d) => d.id !== item.id); item.born = performance.now(); item.seed = hash(JSON.stringify(item)); this.drawings.push(item); }
  highlight(msg) { this._dropId(msg.id); this._add({ kind: "highlight", ...msg }); }
  fib(msg) { this._dropId(msg.id); this._add({ kind: "fib", ...msg }); }
  path(msg) { this._dropId(msg.id); this._add({ kind: "path", ...msg }); }
  arrow(msg) { this._dropId(msg.id); this._add({ kind: "arrow", ...msg }); }
  note(msg) { this._dropId(msg.id); this._add({ kind: "note", ...msg }); if (typeof msg.time === "number") this.ping(msg.time, msg.price); }
  vline(msg) { this._dropId(msg.id); this._add({ kind: "vline", ...msg }); }
  channel(msg) { this._dropId(msg.id); this._add({ kind: "channel", ...msg }); }
  pitchfork(msg) { this._dropId(msg.id); this._add({ kind: "pitchfork", ...msg }); }
  fibExt(msg) { this._dropId(msg.id); this._add({ kind: "fibext", ...msg }); }
  fibFan(msg) { this._dropId(msg.id); this._add({ kind: "fibfan", ...msg }); }
  measure(msg) { this._dropId(msg.id); this._add({ kind: "measure", ...msg }); }
  position(msg) {
    this._dropId(msg.id);
    const rr = Math.abs(msg.target - msg.entry) / Math.max(1e-9, Math.abs(msg.entry - msg.stop));
    this._add({ kind: "position", ...msg, rr });
    this._priceLine({ id: msg.id ? msg.id + ":e" : null, user: msg.user }, msg.entry, "entry", TV.text, "solid", true);
    this.ping(msg.time, msg.entry);
  }
  pattern(msg) {
    this._dropId(msg.id);
    this._add({ ...msg, kind: "pattern", shape: msg.kind });     // msg.kind is the pattern name; the overlay kind stays "pattern"
    if (typeof msg.neckline === "number") this._priceLine({ id: msg.id ? msg.id + ":nl" : null, user: msg.user, state: msg.state }, msg.neckline, "neckline", msg.color || "#e879f9", "dashed", false);
  }
  alert(msg) {
    this._dropId(msg.id);
    const id = msg.id || ("alert" + hash(String(msg.price)));
    this._add({ kind: "alert", ...msg, id, armed: true });
    this._priceLine({ id: id + ":pl", user: msg.user }, msg.price, "🔔 " + (msg.label || "alert"), msg.color || TV.down, "dotted", true);
  }
  _checkAlerts(prev, now) {
    for (const d of this.drawings) {
      if (d.kind !== "alert" || !d.armed) continue;
      const up = prev < d.price && now >= d.price, dn = prev > d.price && now <= d.price;
      if (up || dn) { d.armed = false; d.fired = performance.now(); this._flashUntil = performance.now() + 2500; if (this.onAlert) this.onAlert({ id: d.id, label: d.label || "alert", price: d.price, direction: up ? "up" : "down" }); }
    }
  }
  session(msg) {
    this._dropId(msg.id);
    const cs = this.candles; if (!cs.length) return;
    let start = msg.start, end = msg.end;
    if (!(start && end) && SESSIONS[msg.name]) {     // the most recent occurrence of that session in the loaded bars
      const [h1, h2] = SESSIONS[msg.name]; const last = cs[cs.length - 1].time;
      for (let day = Math.floor(last / 86400); day >= Math.floor(cs[0].time / 86400); day--) {
        const s = day * 86400 + h1 * 3600, e = day * 86400 + h2 * 3600;
        if (s <= last && cs.some((c) => c.time >= s && c.time < e)) { start = s; end = Math.min(e, last + (TF_S[this.tf] || 60)); break; }
      }
    }
    if (!(start && end)) return;
    const seg = cs.filter((c) => c.time >= start && c.time < end); if (!seg.length) return;
    const hi = Math.max(...seg.map((c) => c.high)), lo = Math.min(...seg.map((c) => c.low));
    const name = { asia: "Asia", london: "London", newyork: "New York", custom: "session" }[msg.name] || "session";
    this._add({ kind: "session", id: msg.id || null, user: msg.user, start, end, hi, lo, name, levels: msg.levels !== false, color: { asia: "#f59e0b", london: "#26a69a", newyork: "#2962ff" }[msg.name] || TV.blue });
  }
  keylevels(msg) {
    this._dropId(msg.id);
    const cs = this.candles; if (cs.length < 2) return;
    const last = cs[cs.length - 1], day = Math.floor(last.time / 86400), week = Math.floor((last.time - 4 * 86400) / (7 * 86400));   // weeks start Monday
    const inRange = (a, b) => cs.filter((c) => c.time >= a && c.time < b);
    const prevDay = inRange((day - 1) * 86400, day * 86400), curDay = inRange(day * 86400, (day + 1) * 86400);
    const prevWeek = inRange((week - 1) * 7 * 86400 + 4 * 86400, week * 7 * 86400 + 4 * 86400), curWeek = inRange(week * 7 * 86400 + 4 * 86400, (week + 1) * 7 * 86400 + 4 * 86400);
    const want = new Set(msg.which || ["pdh", "pdl", "dopen"]);
    const lv = [];
    if (prevDay.length) { if (want.has("pdh")) lv.push(["PDH", Math.max(...prevDay.map((c) => c.high)), TV.down]); if (want.has("pdl")) lv.push(["PDL", Math.min(...prevDay.map((c) => c.low)), TV.up]); if (want.has("pdo")) lv.push(["PD open", prevDay[0].open, TV.muted]); }
    if (curDay.length && want.has("dopen")) lv.push(["day open", curDay[0].open, TV.muted]);
    if (prevWeek.length) { if (want.has("pwh")) lv.push(["PWH", Math.max(...prevWeek.map((c) => c.high)), TV.down]); if (want.has("pwl")) lv.push(["PWL", Math.min(...prevWeek.map((c) => c.low)), TV.up]); }
    if (curWeek.length && want.has("wopen")) lv.push(["week open", curWeek[0].open, TV.muted]);
    lv.forEach(([t, p, c], i) => this._priceLine({ id: msg.id ? `${msg.id}:${i}` : null, user: msg.user }, p, t, msg.color && msg.color !== "#787b86" ? msg.color : c, "dotted", true));
  }
  vprofile(msg) {
    this._dropId(msg.id);
    const seg = this.candles.filter((c) => c.time >= msg.start && c.time <= msg.end); if (seg.length < 5) return;
    const prof = this._profile(seg, msg.rows || 24); if (!prof) return;
    const vp = new VolumeProfile(this.chart, this.series, { time: seg[Math.max(0, seg.length - 1)].time, profile: prof.profile, width: Math.max(6, Math.min(30, Math.floor(seg.length / 3))) });
    this._attach(vp, msg.id, msg.user);
    if (msg.user) this.userItems.push({ kind: "prim", obj: vp });
    this._add({ kind: "vprofile", id: msg.id ? msg.id + ":lv" : null, user: msg.user, start: msg.start, end: msg.end, poc: prof.poc, vah: prof.vah, val: prof.val, label: msg.label || "" });
  }
  avwap(msg) {
    this._dropId(msg.id);
    const i0 = this._idx(msg.anchor); const cs = this.candles; if (i0 < 0 || cs.length - i0 < 2) return;
    const pts = []; let pv = 0, vv = 0;
    for (let i = i0; i < cs.length; i++) { const c = cs[i], v = c.volume || 1, tp = (c.high + c.low + c.close) / 3; pv += tp * v; vv += v; pts.push({ time: c.time, value: pv / vv }); }
    const s = this.chart.addSeries(LineSeries, { color: msg.color || "#ff9800", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: msg.label || "AVWAP", visible: !this.hidden, autoscaleInfoProvider: () => null });
    s.setData(pts);
    this.indicators.push({ obj: s, id: msg.id || null, user: !!msg.user, kind: "avwap", spec: msg });
    if (msg.user) this.userItems.push({ kind: "series", obj: s });
    this._add({ kind: "vline", id: msg.id ? msg.id + ":a" : null, user: msg.user, time: msg.anchor, label: msg.label || "anchor", color: msg.color || "#ff9800", style: "dotted" });
  }
  regression(msg) {
    this._dropId(msg.id);
    const cs = this.candles; const a = this._idx(msg.start), b = this._idx(msg.end); if (b - a < 4) return;
    const n = b - a + 1; let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (let i = a; i <= b; i++) { const x = i - a, y = cs[i].close; sx += x; sy += y; sxx += x * x; sxy += x * y; }
    const slope = (n * sxy - sx * sy) / Math.max(1e-9, n * sxx - sx * sx), icpt = (sy - slope * sx) / n;
    let ss = 0; for (let i = a; i <= b; i++) { const r = cs[i].close - (icpt + slope * (i - a)); ss += r * r; }
    const sd = Math.sqrt(ss / n) * (msg.deviations || 2);
    this._add({ kind: "regression", ...msg, t1: cs[a].time, t2: cs[b].time, y1: icpt, y2: icpt + slope * (b - a), sd, slope });
  }
  study(msg) {
    this._dropId(msg.id);
    const spec = { ...msg }; const id = msg.id || `study:${msg.kind}:${msg.length || ""}`;
    this._dropId(id);
    this._buildStudy(spec, id);
  }
  _buildStudy(spec, id) {
    const cs = this.candles; if (cs.length < 5) return false;
    const closes = cs.map((c) => c.close), col = spec.color || TV.blue, user = !!spec.user;
    // no axis tags for studies: the legend names them, and the price scale stays readable for the levels that matter
    const line = (pts, opts, pane) => { const s = this.chart.addSeries(LineSeries, { lineWidth: 2, priceLineVisible: false, lastValueVisible: false, visible: !this.hidden, ...(pane ? {} : { autoscaleInfoProvider: () => null }), ...opts }, pane || 0); s.setData(pts.filter((p) => p.value != null)); this.indicators.push({ obj: s, id, user, kind: spec.kind, spec, pane: pane || 0 }); if (user) this.userItems.push({ kind: "series", obj: s }); return s; };
    const zip = (vals) => cs.map((c, i) => ({ time: c.time, value: vals[i] }));
    const k = spec.kind, n = spec.length || 20;
    if (k === "ema") line(zip(ema(closes, n)), { color: col, title: `EMA ${n}` });
    else if (k === "sma") line(zip(sma(closes, n)), { color: col, title: `SMA ${n}` });
    else if (k === "bollinger") { const m = sma(closes, n), sd = stdev(closes, n), mult = spec.mult || 2; line(zip(m), { color: col, title: `BB ${n}` }); line(zip(m.map((v, i) => v == null ? null : v + mult * sd[i])), { color: rgba(col, 0.6), lineWidth: 1, lastValueVisible: false }); line(zip(m.map((v, i) => v == null ? null : v - mult * sd[i])), { color: rgba(col, 0.6), lineWidth: 1, lastValueVisible: false }); }
    else if (k === "vwap") { const pts = []; let pv = 0, vv = 0, day = -1; for (const c of cs) { const d = Math.floor(c.time / 86400); if (d !== day) { day = d; pv = 0; vv = 0; } const v = c.volume || 1; pv += (c.high + c.low + c.close) / 3 * v; vv += v; pts.push({ time: c.time, value: pv / vv }); } line(pts, { color: col, title: "VWAP" }); }
    else if (k === "rsi") { const s = line(zip(rsi(closes, n)), { color: col, title: `RSI ${n}` }, 1); s.createPriceLine({ price: 70, color: TV.muted, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" }); s.createPriceLine({ price: 30, color: TV.muted, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" }); this._paneSize(1); }
    else if (k === "macd") { const f = ema(closes, spec.fast || 12), sl = ema(closes, spec.slow || 26); const macd = f.map((v, i) => v == null || sl[i] == null ? null : v - sl[i]); const valid = macd.map((v) => v == null ? 0 : v); const sig = ema(valid, spec.signal || 9).map((v, i) => macd[i] == null ? null : v); const pane = this._nextPane(); const h = this.chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false, visible: !this.hidden, title: "MACD" }, pane); h.setData(cs.map((c, i) => ({ time: c.time, value: macd[i] == null || sig[i] == null ? 0 : macd[i] - sig[i], color: (macd[i] || 0) - (sig[i] || 0) >= 0 ? "rgba(8,153,129,.6)" : "rgba(242,54,69,.6)" }))); this.indicators.push({ obj: h, id, user, kind: "macd", spec, pane }); line(zip(macd), { color: col, lineWidth: 2 }, pane); line(zip(sig), { color: "#ff9800", lineWidth: 1 }, pane); this._paneSize(pane); }
    else if (k === "atr") { line(zip(atr(cs, n)), { color: col, title: `ATR ${n}` }, this._nextPane()); this._paneSize(this.indicators[this.indicators.length - 1].pane); }
    else return false;
    return true;
  }
  _nextPane() { const used = new Set(this.indicators.map((s) => s.pane).filter((p) => p > 0)); let p = 1; while (used.has(p)) p++; return Math.min(p, this.chart.panes().length); }
  _paneSize(idx) { try { const panes = this.chart.panes(); if (panes[0]) panes[0].setStretchFactor(4); if (panes[idx]) panes[idx].setStretchFactor(1); } catch (e) { /* older build */ } }
  _recomputeStudies() {
    // bar history changed (new bar or older bars prepended): rebuild computed studies from the candles
    const specs = this.indicators.filter((s) => s.spec && (s.kind !== "avwap")).map((s) => ({ id: s.id, spec: s.spec }));
    const seen = new Set();
    for (const { id, spec } of specs) { if (seen.has(id)) continue; seen.add(id); this._dropId(id); this._buildStudy(spec, id); }
    for (const s of this.indicators.filter((x) => x.kind === "avwap")) { const spec = s.spec; this._dropId(s.id); this.avwap({ ...spec }); }
  }
  _updateStudiesLast() { /* intrabar: studies refresh on the next closed bar (what "confirmed" means) */ }
  indicator(msg) {
    this._dropId(msg.id);
    const s = this.chart.addSeries(LineSeries, { color: msg.color || TV.blue, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: msg.name || "", visible: !this.hidden, autoscaleInfoProvider: () => null });
    const pts = (msg.points || []).filter((p) => typeof p.value === "number").sort((a, b) => a.time - b.time).filter((p, i, a) => i === 0 || p.time > a[i - 1].time);
    s.setData(pts);
    this.indicators.push({ obj: s, id: msg.id || null, user: !!msg.user, kind: "points" });
  }
  zoom(msg) { if (this.candles.length && this._autoOk()) { try { this.chart.timeScale().setVisibleRange({ from: msg.start, to: msg.end }); } catch (e) { /* no data in range */ } } }

  clear() {
    const keep = this.locked;      // Lock: the operator's own drawings survive a lesson's clear
    this.markerList = keep ? this.markerList.filter((m) => m.user) : []; this.markers.setMarkers(this.hidden ? [] : this.markerList);
    for (const pl of this.priceLines) if (!(keep && pl.user)) { try { this.series.removePriceLine(pl.obj); } catch (e) { /* gone */ } }
    this.priceLines = keep ? this.priceLines.filter((x) => x.user) : [];
    this.drawings = keep ? this.drawings.filter((d) => d.user) : [];
    for (const p of this.primitives) if (!(keep && p.user)) { try { this.series.detachPrimitive(p.obj); } catch (e) { /* gone */ } }
    this.primitives = keep ? this.primitives.filter((x) => x.user) : [];
    for (const s of this.indicators) if (!(keep && s.user)) { try { this.chart.removeSeries(s.obj); } catch (e) { /* gone */ } }
    this.indicators = keep ? this.indicators.filter((x) => x.user) : [];
    if (!keep) { this.userItems = []; if (this.rectTool) { try { this.rectTool.remove(); } catch (e) { /* gone */ } this.rectTool = null; } }
  }

  // ---- overlay (TradingView look: thin solid lines, round handles, small label chips) ----
  _line(ctx, x1, y1, x2, y2, prog, width, color, dashed) {
    const x2p = x1 + (x2 - x1) * prog, y2p = y1 + (y2 - y1) * prog;
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = "butt"; ctx.setLineDash(dashed ? [6, 5] : []);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2p, y2p); ctx.stroke(); ctx.setLineDash([]);
  }
  _handle(ctx, x, y, color) { ctx.fillStyle = TV.bg; ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
  _chip(ctx, text, x, y, color, size = 13) {
    if (!text) return;
    ctx.font = `600 ${size}px ${FONT}`; const w = ctx.measureText(text).width;
    if (x + w + 10 > this.overlay.width - 70) x = Math.max(4, x - w - 22);   // keep chips off the price axis
    ctx.fillStyle = color; ctx.beginPath(); ctx.roundRect(x, y - size - 4, w + 10, size + 8, 3); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.textBaseline = "alphabetic"; ctx.fillText(text, x + 5, y - 2);
  }
  _text(ctx, text, x, y, color, size = 12, weight = 500) { ctx.font = `${weight} ${size}px ${FONT}`; ctx.fillStyle = color; ctx.textBaseline = "alphabetic"; ctx.fillText(text, x, y); }
  _extendToEdge(x1, y1, x2, y2, W, mode) {
    // extend the segment (x1,y1)-(x2,y2) to the right edge (and the left edge when mode === "both")
    if (Math.abs(x2 - x1) < 1e-6) return [x1, y1, x2, y2];
    const k = (y2 - y1) / (x2 - x1);
    const right = Math.max(x1, x2) <= W ? [W, y1 + k * (W - x1)] : [x2, y2];
    const left = mode === "both" ? [0, y1 + k * (0 - x1)] : [Math.min(x1, x2) === x1 ? x1 : x2, Math.min(x1, x2) === x1 ? y1 : y2];
    return [left[0], left[1], right[0], right[1]];
  }

  _countdown(ctx, W) {
    const n = this.candles.length; if (!n) return;
    const last = this.candles[n - 1], step = TF_S[this.tf] || 60;
    const left = Math.max(0, last.time + step - Math.floor(Date.now() / 1000));
    const h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60), sec = left % 60;
    const txt = h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    const py = this.series.priceToCoordinate(last.close); if (py == null) return;
    const scaleW = this.chart.priceScale("right").width(); const x0 = W - scaleW;
    ctx.font = `500 11px ${FONT}`; ctx.fillStyle = last.close >= last.open ? TV.up : TV.down;
    ctx.beginPath(); ctx.roundRect(x0 + 2, py + 10, scaleW - 4, 16, 2); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.textBaseline = "middle"; ctx.fillText(txt, x0 + 6, py + 18); ctx.textBaseline = "alphabetic";
  }

  drawOverlay() {
    const ctx = this.ctx, W = this.overlay.width, H = this.overlay.height, now = performance.now();
    ctx.clearRect(0, 0, W, H);
    if (this._pingUntil && now > this._pingUntil) { try { this.chart.clearCrosshairPosition(); } catch (e) { /* noop */ } this._pingUntil = 0; }
    if (this.candles.length && (TF_S[this.tf] || 0) <= 86400) { this._countdown(ctx, W); }
    if (this.hidden) return;
    // drawings live in the price pane only; studies below keep their own space
    let paneH = H; try { const p0 = this.chart.panes()[0]; if (p0 && p0.getHeight) paneH = p0.getHeight() || H; } catch (e) { /* older build */ }
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, paneH); ctx.clip();
    if (this._flashUntil && now < this._flashUntil) { ctx.fillStyle = `rgba(242,54,69,${0.08 * (0.5 + 0.5 * Math.sin(now / 90))})`; ctx.fillRect(0, 0, W, paneH); }
    const ts = this.chart.timeScale();
    const x = (t) => ts.timeToCoordinate(t);
    const y = (p) => this.series.priceToCoordinate(p);
    const xr = (t) => {
      const v = x(t); if (v != null) return v;
      const cs = this.candles; if (!cs.length) return null;
      if (t < cs[0].time) return 0; if (t > cs[cs.length - 1].time) return W;
      let lo = 0, hi = cs.length - 1; while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (cs[mid].time <= t) lo = mid; else hi = mid; }
      const xa = x(cs[lo].time), xb = x(cs[hi].time); if (xa == null || xb == null) return xa != null ? xa : xb;
      return xa + (xb - xa) * ((t - cs[lo].time) / Math.max(1, cs[hi].time - cs[lo].time));
    };
    const axisX = W - 70;
    for (const d of this.drawings) {
      const prog = Math.min(1, (now - d.born) / DRAW_MS), st = this._stateOf(d), col = st.color || d.color || TV.blue;
      const dashed = st.dashed === true || (st.dashed == null && !!d.dashed);
      const lbl = (t) => (t ? st.prefix + t : "");
      if (d.kind === "highlight") {
        const a = xr(d.start), b = xr(d.end); if (a == null && b == null) continue;
        const x1 = a == null ? 0 : a, x2 = b == null ? W : b;
        ctx.fillStyle = "rgba(41,98,255,0.07)"; ctx.fillRect(Math.min(x1, x2), 0, Math.abs(x2 - x1) * prog, paneH);   // one calm tint, never a coloured band
        if (d.label) this._chip(ctx, lbl(d.label), Math.min(x1, x2) + 6, 60, TV.blue);
      } else if (d.kind === "label") {
        const lx = xr(d.time), ly = y(d.price); if (lx == null || ly == null) continue;
        this._chip(ctx, d.text, lx + (d.dx || 6), ly - 4, col);
      } else if (d.kind === "line") {
        const x1 = xr(d.t1), y1 = y(d.p1), x2 = xr(d.t2), y2 = y(d.p2); if ([x1, y1, x2, y2].some((v) => v == null)) continue;
        const e = d.toEdge ? this._extendToEdge(x1, y1, x2, y2, axisX, d.toEdge) : [x1, y1, x2, y2];
        this._line(ctx, e[0], e[1], e[2], e[3], prog, d.width || 2, col, dashed);
      } else if (d.kind === "vline") {
        const vx = xr(d.time); if (vx == null) continue;
        this._line(ctx, vx, 0, vx, paneH, prog, 1, col, d.style !== "solid");
        if (d.label) this._chip(ctx, lbl(d.label), vx + 4, 28, col);
      } else if (d.kind === "arrow") {
        const x1 = xr(d.t1), y1 = y(d.p1), x2 = xr(d.t2), y2 = y(d.p2); if ([x1, y1, x2, y2].some((v) => v == null)) continue;
        this._line(ctx, x1, y1, x2, y2, prog, 2, col, dashed);
        if (prog >= 1) { const ang = Math.atan2(y2 - y1, x2 - x1); ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - 12 * Math.cos(ang - 0.45), y2 - 12 * Math.sin(ang - 0.45)); ctx.lineTo(x2 - 12 * Math.cos(ang + 0.45), y2 - 12 * Math.sin(ang + 0.45)); ctx.closePath(); ctx.fill(); }
        if (d.label) this._chip(ctx, lbl(d.label), (x1 + x2) / 2 + 6, (y1 + y2) / 2 - 6, col);
      } else if (d.kind === "fib") {
        const x1 = xr(d.t1), x2 = xr(d.t2), yA = y(d.p1), yB = y(d.p2); if ([x1, x2, yA, yB].some((v) => v == null)) continue;
        const left = Math.min(x1, x2), right = Math.min(axisX, Math.max(x1, x2) + 140);
        const lv = [0, ...(d.levels || [0.382, 0.5, 0.618, 0.786]), 1];
        const cols = ["#787b86", "#f23645", "#ff9800", "#4caf50", "#089981", "#2962ff", "#787b86"];
        lv.forEach((l, i) => {
          if (i / lv.length > prog) return;
          const py = yA + (yB - yA) * (1 - l), price = d.p1 + (d.p2 - d.p1) * (1 - l), c = st.color || cols[i % cols.length];
          if (i < lv.length - 1) { const pyn = yA + (yB - yA) * (1 - lv[i + 1]); ctx.fillStyle = rgba(c, 0.08); ctx.fillRect(left, Math.min(py, pyn), right - left, Math.abs(pyn - py)); }
          this._line(ctx, left, py, right, py, 1, 1, c, dashed);
          this._text(ctx, `${l.toFixed(3)} (${fmtP(price)})`, left + 4, py - 3, c);
        });
        this._line(ctx, x1, yA, x2, yB, 1, 1, TV.muted, true); this._handle(ctx, x1, yA, TV.muted); this._handle(ctx, x2, yB, TV.muted);
      } else if (d.kind === "fibext") {
        // levels projected from C by the size of the A->B leg
        const xa = xr(d.t1), xb = xr(d.t2), xc = xr(d.t3), ya = y(d.p1), yb = y(d.p2), yc = y(d.p3); if ([xa, xb, xc, ya, yb, yc].some((v) => v == null)) continue;
        this._line(ctx, xa, ya, xb, yb, prog, 1, TV.muted, true); this._line(ctx, xb, yb, xc, yc, prog, 1, TV.muted, true);
        [[xa, ya, "A"], [xb, yb, "B"], [xc, yc, "C"]].forEach(([px, py, t]) => { this._handle(ctx, px, py, TV.muted); this._text(ctx, t, px + 6, py - 6, TV.muted, 12, 700); });
        const leg = d.p2 - d.p1, right = Math.min(axisX, xc + 160);
        (d.levels || [0.618, 1, 1.272, 1.618, 2]).forEach((l, i) => {
          if (i / (d.levels || [1]).length > prog) return;
          const price = d.p3 + leg * l, py = y(price); if (py == null) return;
          this._line(ctx, xc, py, right, py, 1, 1, col, false); this._text(ctx, `${l.toFixed(3)} (${fmtP(price)})`, xc + 4, py - 3, col);
        });
      } else if (d.kind === "fibfan") {
        const x1 = xr(d.t1), x2 = xr(d.t2), y1 = y(d.p1), y2 = y(d.p2); if ([x1, x2, y1, y2].some((v) => v == null)) continue;
        this._line(ctx, x1, y1, x2, y2, prog, 1, TV.muted, true); this._handle(ctx, x1, y1, TV.muted); this._handle(ctx, x2, y2, TV.muted);
        (d.levels || [0.382, 0.5, 0.618]).forEach((l) => {
          const py = y(d.p1 + (d.p2 - d.p1) * (1 - l)); if (py == null) return;
          const e = this._extendToEdge(x1, y1, x2, py, axisX, "right"); this._line(ctx, e[0], e[1], e[2], e[3], prog, 1, col, false);
          this._text(ctx, l.toFixed(3), Math.min(axisX - 40, e[2] - 36), e[3] - 4, col);
        });
      } else if (d.kind === "channel") {
        const x1 = xr(d.t1), x2 = xr(d.t2), x3 = xr(d.t3), y1 = y(d.p1), y2 = y(d.p2), y3 = y(d.p3); if ([x1, x2, x3, y1, y2, y3].some((v) => v == null)) continue;
        const k = Math.abs(x2 - x1) < 1e-6 ? 0 : (y2 - y1) / (x2 - x1); const off = y3 - (y1 + k * (x3 - x1));
        const base = d.extend === false ? [x1, y1, x2, y2] : this._extendToEdge(x1, y1, x2, y2, axisX, "right");
        const par = [base[0], base[1] + off, base[2], base[3] + off];
        ctx.fillStyle = rgba(col, 0.08); ctx.beginPath(); ctx.moveTo(base[0], base[1]); ctx.lineTo(base[0] + (base[2] - base[0]) * prog, base[1] + (base[3] - base[1]) * prog); ctx.lineTo(par[0] + (par[2] - par[0]) * prog, par[1] + (par[3] - par[1]) * prog); ctx.lineTo(par[0], par[1]); ctx.closePath(); ctx.fill();
        this._line(ctx, base[0], base[1], base[2], base[3], prog, 2, col, dashed); this._line(ctx, par[0], par[1], par[2], par[3], prog, 2, col, dashed);
        const mid = [base[0], (base[1] + par[1]) / 2, base[2], (base[3] + par[3]) / 2]; this._line(ctx, mid[0], mid[1], mid[2], mid[3], prog, 1, col, true);
        if (prog >= 1) { this._handle(ctx, x1, y1, col); this._handle(ctx, x2, y2, col); this._handle(ctx, x3, y3, col); }
        if (d.label) this._chip(ctx, lbl(d.label), x2 + 8, y2 - 6, col);
      } else if (d.kind === "regression") {
        const x1 = xr(d.t1), x2 = xr(d.t2), y1 = y(d.y1), y2 = y(d.y2), yu = y(d.y1 + d.sd), yl = y(d.y1 - d.sd); if ([x1, x2, y1, y2, yu, yl].some((v) => v == null)) continue;
        const dy = yu - y1;   // band offset in pixels (constant along the line)
        ctx.fillStyle = rgba(col, 0.08); ctx.beginPath(); ctx.moveTo(x1, y1 + dy); ctx.lineTo(x2, y2 + dy); ctx.lineTo(x2, y2 - dy); ctx.lineTo(x1, y1 - dy); ctx.closePath(); ctx.fill();
        this._line(ctx, x1, y1, x2, y2, prog, 2, col, false); this._line(ctx, x1, y1 + dy, x2, y2 + dy, prog, 1, col, true); this._line(ctx, x1, y1 - dy, x2, y2 - dy, prog, 1, col, true);
        this._chip(ctx, lbl(d.label || `regression ${d.slope >= 0 ? "up" : "down"}`), x2 + 8, y2 - 6, col);
      } else if (d.kind === "pitchfork") {
        const x1 = xr(d.t1), x2 = xr(d.t2), x3 = xr(d.t3), y1 = y(d.p1), y2 = y(d.p2), y3 = y(d.p3); if ([x1, x2, x3, y1, y2, y3].some((v) => v == null)) continue;
        const mx = (x2 + x3) / 2, my = (y2 + y3) / 2; const e = this._extendToEdge(x1, y1, mx, my, axisX, "right");
        this._line(ctx, e[0], e[1], e[2], e[3], prog, 2, col, dashed);
        for (const [px, py] of [[x2, y2], [x3, y3]]) { const off = py - my; const ee = [mx, my + off, e[2], e[3] + off]; this._line(ctx, ee[0], ee[1], ee[2], ee[3], prog, 1, col, true); }
        this._line(ctx, x2, y2, x3, y3, 1, 1, TV.muted, true);
        [[x1, y1], [x2, y2], [x3, y3]].forEach(([px, py]) => this._handle(ctx, px, py, col));
        if (d.label) this._chip(ctx, lbl(d.label), x1 + 8, y1 - 6, col);
      } else if (d.kind === "position") {
        const x0 = xr(d.time), ye = y(d.entry), ys = y(d.stop), yt = y(d.target); if ([x0, ye, ys, yt].some((v) => v == null)) continue;
        const x1 = Math.min(axisX, x0 + Math.max(120, (axisX - x0) * 0.6));
        ctx.fillStyle = "rgba(8,153,129,0.16)"; ctx.fillRect(x0, Math.min(ye, yt), (x1 - x0) * prog, Math.abs(yt - ye));
        ctx.fillStyle = "rgba(242,54,69,0.16)"; ctx.fillRect(x0, Math.min(ye, ys), (x1 - x0) * prog, Math.abs(ys - ye));
        this._line(ctx, x0, ye, x1, ye, prog, 1, TV.text, false); this._line(ctx, x0, yt, x1, yt, prog, 1, TV.up, false); this._line(ctx, x0, ys, x1, ys, prog, 1, TV.down, false);
        const risk = Math.abs(d.entry - d.stop), rew = Math.abs(d.target - d.entry);
        this._chip(ctx, `target ${fmtP(d.target)}  +${(rew / d.entry * 100).toFixed(2)}%`, x0 + 4, yt - 2, TV.up, 12);
        this._chip(ctx, `stop ${fmtP(d.stop)}  -${(risk / d.entry * 100).toFixed(2)}%`, x0 + 4, ys + 16, TV.down, 12);
        this._chip(ctx, `${d.side} · R:R ${d.rr.toFixed(2)} · risk ${d.risk_pct || 1}% of account`, x0 + 4, ye - 2, TV.text, 12);
        if (d.label) this._chip(ctx, lbl(d.label), x1 - 60, ye - 20, col);
      } else if (d.kind === "measure") {
        const x1 = xr(d.t1), y1 = y(d.p1), x2 = xr(d.t2), y2 = y(d.p2); if ([x1, y1, x2, y2].some((v) => v == null)) continue;
        const up = d.p2 >= d.p1, c = up ? TV.up : TV.down;
        ctx.fillStyle = rgba(c, 0.12); ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1) * prog, Math.abs(y2 - y1));
        ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.setLineDash([4, 4]); ctx.strokeRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1) * prog, Math.abs(y2 - y1)); ctx.setLineDash([]);
        const bars = Math.abs(this._idx(d.t2) - this._idx(d.t1)), secs = Math.abs(d.t2 - d.t1);
        const dur = secs >= 86400 ? `${(secs / 86400).toFixed(1)}d` : secs >= 3600 ? `${(secs / 3600).toFixed(1)}h` : `${Math.round(secs / 60)}m`;
        const txt = `${up ? "+" : ""}${(d.p2 - d.p1).toFixed(d.p1 >= 100 ? 1 : 4)} (${up ? "+" : ""}${((d.p2 - d.p1) / d.p1 * 100).toFixed(2)}%)  ${bars} bars · ${dur}`;
        this._chip(ctx, txt, Math.min(x1, x2) + 4, Math.min(y1, y2) - 6, c, 13);
      } else if (d.kind === "path" || d.kind === "pattern") {
        const pts = (d.points || []).map((p) => [xr(p.time), y(p.price)]).filter((p) => p[0] != null && p[1] != null);
        const total = pts.length - 1, upto = Math.max(1, Math.floor(total * prog + 1));
        for (let i = 1; i < Math.min(pts.length, upto + 1); i++) this._line(ctx, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1], i === upto ? ((total * prog) % 1) || 1 : 1, d.width || (d.kind === "pattern" ? 2 : 1.5), col, dashed);
        if (prog >= 1) for (const p of pts) this._handle(ctx, p[0], p[1], col);
        if (d.labels) d.labels.forEach((t, i) => { if (pts[i] && t) { const pt = d.points[i]; const above = i > 0 && d.points[i - 1] && pt.price >= d.points[i - 1].price; this._text(ctx, t, pts[i][0] - 4, pts[i][1] + (above ? -9 : 17), col, 13, 700); } });
        if (d.kind === "pattern" && pts.length >= 3 && ["triangle", "wedge", "flag", "channel", "rectangle"].includes(d.shape || "")) {
          // boundary lines through alternating corners make a triangle / wedge / flag readable at a glance
          const even = pts.filter((_, i) => i % 2 === 0), odd = pts.filter((_, i) => i % 2 === 1);
          for (const arr of [even, odd]) if (arr.length >= 2) { const a = arr[0], b = arr[arr.length - 1]; const e = this._extendToEdge(a[0], a[1], b[0], b[1], Math.min(axisX, b[0] + 120), "right"); this._line(ctx, e[0], e[1], e[2], e[3], prog, 1, col, true); }
        }
        const tag = d.label || (d.kind === "pattern" ? (d.shape || "").replace(/_/g, " ") : "");
        if (tag && pts.length) this._chip(ctx, lbl(tag), pts[pts.length - 1][0] + 8, pts[pts.length - 1][1], col);
      } else if (d.kind === "session") {
        const a = xr(d.start), b = xr(d.end); if (a == null && b == null) continue;
        const x1 = a == null ? 0 : a, x2 = b == null ? W : b;
        ctx.fillStyle = rgba(d.color, 0.07); ctx.fillRect(Math.min(x1, x2), 0, Math.abs(x2 - x1) * prog, paneH);
        this._chip(ctx, d.name, Math.min(x1, x2) + 6, 84, d.color);
        if (d.levels && prog >= 1) { for (const [p, t] of [[d.hi, `${d.name} high`], [d.lo, `${d.name} low`]]) { const py = y(p); if (py == null) continue; this._line(ctx, Math.min(x1, x2), py, axisX, py, 1, 1, d.color, true); this._text(ctx, `${t} ${fmtP(p)}`, Math.max(x1, x2) + 6, py - 3, d.color, 12, 600); } }
      } else if (d.kind === "vprofile") {
        const a = xr(d.start), b = xr(d.end); if (a == null || b == null) continue;
        for (const [p, t, c] of [[d.poc, "POC", "#ff9800"], [d.vah, "VAH", TV.blue], [d.val, "VAL", TV.blue]]) { const py = y(p); if (py == null) continue; this._line(ctx, a, py, Math.min(axisX, b + 60), py, prog, t === "POC" ? 2 : 1, c, t !== "POC"); this._text(ctx, `${t} ${fmtP(p)}`, a + 4, py - 3, c, 12, 600); }
        if (d.label) this._chip(ctx, lbl(d.label), a + 6, 108, "#ff9800");
      } else if (d.kind === "alert") {
        const py = y(d.price); if (py == null) continue;
        const fired = d.fired && now - d.fired < 2500;
        ctx.font = `${fired ? 22 : 16}px ${FONT}`; ctx.textBaseline = "middle"; ctx.fillText("🔔", axisX - 26, py); ctx.textBaseline = "alphabetic";
        if (fired) this._chip(ctx, `alert: ${d.label || ""} ${fmtP(d.price)}`, axisX - 220, py - 10, TV.down, 14);
      } else if (d.kind === "note") {
        const nx = xr(d.time), ny = y(d.price); if (nx == null || ny == null) continue;
        const size = Math.max(10, Math.min(72, d.size || 15)), lines = String(d.text || "").split("\n");
        const shown = Math.ceil(lines.join(" ").length * prog);
        ctx.font = `600 ${size}px ${FONT}`; const w = Math.max(...lines.map((l) => ctx.measureText(l).width), 8), lh = size * 1.25, h = lh * lines.length;
        const x0 = nx + w + 14 > W - 70 ? nx - w - 12 : nx + 1;      // flip to the left near the price axis
        ctx.fillStyle = d.bg || "rgba(19,23,34,.94)"; ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.beginPath(); ctx.roundRect(x0 - 5, ny - h - 4, w + 12, h + 10, 3); ctx.fill(); if (!d.bg || d.bg === "transparent") ctx.stroke();
        ctx.fillStyle = col; let used = 0;
        lines.forEach((l, i) => { const part = l.slice(0, Math.max(0, shown - used)); used += l.length + 1; ctx.fillText(part, x0, ny - h - 1 + lh * (i + 1) - lh * 0.22); });
        d._box = [x0 - 5, ny - h - 4, w + 12, h + 10];
      }
    }
    ctx.restore();
  }
}
