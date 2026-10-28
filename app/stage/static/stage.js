/* Stage controller: connects to /ws/stage, dispatches messages to the big chart, the room, captions. */
import { ChartEngine } from "./chart.js";

(async function () {
  const $ = (s) => document.querySelector(s);
  const chart = new ChartEngine($("#chart"), $("#overlay"), () => send({ type: "replay_done" }));
  const fmtP = (p) => (p >= 1000 ? p.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : p >= 10 ? p.toFixed(2) : p.toFixed(4));
  chart.onLegend = (c, prev) => {   // TradingView legend: O H L C and change of the last bar
    const up = c.close >= c.open, cls = up ? "lg-v up" : "lg-v down";
    for (const [id, v] of [["#lg-o", c.open], ["#lg-h", c.high], ["#lg-l", c.low], ["#lg-c", c.close]]) { const el = $(id); el.textContent = fmtP(v); el.className = cls; }
    const d = c.close - prev, pct = prev ? (d / prev) * 100 : 0; const el = $("#lg-chg");
    el.textContent = `${d >= 0 ? "+" : ""}${fmtP(Math.abs(d)).replace(/^/, d < 0 ? "-" : "")} (${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)`; el.className = d >= 0 ? "lg-v up" : "lg-v down";
    const v = c.volume || 0; $("#lg-vol").textContent = v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "K" : v ? v.toFixed(0) : "—";
    const cs = chart.candles; if (cs.length >= 20) { let e = cs[cs.length - 20].close; const k = 2 / 21; for (let i = cs.length - 19; i < cs.length; i++) e = cs[i].close * k + e * (1 - k); $("#lg-ema").textContent = fmtP(e); }
  };
  const setTf = (tf) => { $("#lg-tf").textContent = ({ "1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D", "1w": "W" })[tf] || tf; document.querySelectorAll("#tv-tfs button").forEach((b) => b.classList.toggle("on", b.dataset.tf === tf)); };
  setInterval(() => { const d = new Date(); $("#tv-clock").textContent = d.toISOString().slice(11, 19) + " (UTC)"; }, 1000);
  // ---- the TradingView chrome is interactive for the operator ----
  document.querySelectorAll("#tv-tfs button").forEach((b) => b.addEventListener("click", () => {
    setTf(b.dataset.tf); $("#chart-note").textContent = "loading " + b.dataset.tf + "…"; $("#chart-note").style.display = "";
    send({ type: "operator", cmd: "tf", tf: b.dataset.tf });
  }));
  document.querySelectorAll(".tv-ranges button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tv-ranges button").forEach((x) => x.classList.toggle("on", x === b)); chart.setRange(b.textContent.trim());
  }));
  document.querySelectorAll(".tv-foot-right span").forEach((s) => { const k = s.textContent.trim(); if (!["%", "log", "auto"].includes(k)) return;
    s.style.cursor = "pointer";
    s.addEventListener("click", () => { const st = chart.setScaleMode(k); document.querySelectorAll(".tv-foot-right span").forEach((x) => { const kk = x.textContent.trim(); if (kk in st) x.classList.toggle("on", !!st[kk]); }); });
  });
  const leftBtns = document.querySelectorAll("#tv-left button");
  const markTool = (name) => leftBtns.forEach((x) => { if (!["Magnet", "Lock", "Hide"].includes(x.title)) x.classList.toggle("on", x.title === name); });
  const TOGGLES = { Magnet: () => chart.toggleMagnet(), Lock: () => chart.toggleLock(), Hide: () => chart.toggleHidden() };
  leftBtns.forEach((b) => b.addEventListener("click", () => {
    if (TOGGLES[b.title]) { b.classList.toggle("on", TOGGLES[b.title]()); return; }      // magnet / lock / hide are switches, not tools
    const t = chart.setTool(b.title === "Cursor" ? "Cursor" : b.title); markTool(t);
  }));
  const markTool0 = markTool;
  const markToolKeep = (name) => { leftBtns.forEach((x) => { if (!TOGGLES[x.title]) x.classList.toggle("on", x.title === name); }); };
  chart.onToolDone = () => markToolKeep("Cursor");
  // Text tool editor: a small floating box at the click point; letters and numbers go in as typed
  const ed = $("#note-editor"), edText = $("#ne-text"), edSize = $("#ne-size"), edColor = $("#ne-color"), edBg = $("#ne-bg");
  let edTarget = null;
  const edClose = () => { ed.classList.add("hidden"); edTarget = null; };
  const edDone = () => {
    if (!edTarget) return;
    const text = edText.value.trim();
    const style = { size: parseInt(edSize.value, 10) || 16, color: edColor.value, bg: $("#ne-nobg").checked ? "transparent" : edBg.value };
    try { localStorage.setItem("note_style", JSON.stringify(style)); } catch (e) { /* ignore */ }
    if (edTarget.existing) chart.remove({ id: edTarget.existing.id });
    if (text) chart.note({ id: edTarget.existing ? edTarget.existing.id : "txt" + Date.now(), time: edTarget.time, price: edTarget.price, text, ...style, user: true });
    edClose();
  };
  chart.onTextEdit = (t) => {
    edTarget = t;
    let style = { size: 16, color: "#131722", bg: "#ffffff" };
    try { style = { ...style, ...(JSON.parse(localStorage.getItem("note_style") || "{}")) }; } catch (e) { /* ignore */ }
    if (t.existing) style = { size: t.existing.size || style.size, color: t.existing.color || style.color, bg: t.existing.bg || style.bg };
    edText.value = t.existing ? t.existing.text : ""; edSize.value = style.size; edColor.value = style.color.startsWith("#") ? style.color : "#131722";
    $("#ne-nobg").checked = style.bg === "transparent"; edBg.value = style.bg && style.bg.startsWith("#") ? style.bg : "#ffffff";
    const wrap = $("#chart-wrap").getBoundingClientRect(), stage = $("#stage").getBoundingClientRect(); const k = stage.width ? 1080 / stage.width : 1;
    ed.style.left = Math.min(1080 - 340, Math.max(0, (wrap.left - stage.left) * k + t.x)) + "px"; ed.style.top = Math.max(0, (wrap.top - stage.top) * k + t.y + 12) + "px";
    ed.classList.remove("hidden"); edText.focus();
  };
  $("#ne-done").addEventListener("click", edDone); $("#ne-cancel").addEventListener("click", edClose);
  $("#ne-smaller").addEventListener("click", () => { edSize.value = Math.max(10, (parseInt(edSize.value, 10) || 16) - 2); });
  $("#ne-bigger").addEventListener("click", () => { edSize.value = Math.min(72, (parseInt(edSize.value, 10) || 16) + 2); });
  edText.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); edDone(); } else if (e.key === "Escape") edClose(); });
  // a price alert fired on the live candle: the host gets told so he can react to it on air
  chart.onAlert = (a) => send({ type: "operator", cmd: "alert_hit", id: a.id, label: a.label, price: a.price, direction: a.direction });
  // operator dock: visible only while the mouse is moving over the stage; keyboard P / M / S work any time
  let dockT = null;
  const showDock = () => { $("#stage").classList.add("show-dock"); clearTimeout(dockT); dockT = setTimeout(() => $("#stage").classList.remove("show-dock"), 2500); };
  window.addEventListener("mousemove", showDock);
  $("#dock").addEventListener("mouseenter", () => clearTimeout(dockT));
  $("#dock").addEventListener("mouseleave", showDock);
  const op = (cmd) => send({ type: "operator", cmd });
  $("#btn-pause").addEventListener("click", () => op($("#btn-pause").classList.contains("on") ? "resume" : "pause"));
  $("#btn-mute").addEventListener("click", () => op("mute"));
  $("#btn-skip").addEventListener("click", () => op("skip"));
  window.addEventListener("keydown", (e) => {
    if (e.target && /INPUT|TEXTAREA/.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === "p") { op($("#btn-pause").classList.contains("on") ? "resume" : "pause"); showDock(); }
    else if (k === "m") { op("mute"); showDock(); }
    else if (k === "s") { op("skip"); showDock(); }
  });
  let curSymbol = "", curTf = "";
  chart.onNeedHistory = (before) => { if (curSymbol) send({ type: "chart_more", symbol: curSymbol, tf: curTf, before }); };
  setInterval(() => { const st = chart.setScaleMode(null); document.querySelectorAll(".tv-foot-right span").forEach((x) => { const kk = x.textContent.trim(); if (kk in st) x.classList.toggle("on", !!st[kk]); }); }, 1000);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" && document.activeElement !== $("#ne-text")) { markTool(chart.setTool("Cursor")); } });
  // default: the real-person photo room (Trading_Room reference). ?room=3d switches to the three.js room.
  const params = new URLSearchParams(location.search);
  let room;
  if (params.get("room") === "3d") { const { Room3D } = await import("./room3d.js"); room = new Room3D($("#room")); }
  else room = new Room($("#room"));
  let ws = null;
  let captionTimer = null;

  function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }
  function fmtTf(tf) { return tf ? tf.toUpperCase() : ""; }

  function caption(msg) {
    const el = $("#caption");
    if (captionTimer) { clearInterval(captionTimer); captionTimer = null; }
    if (!msg.text) { el.innerHTML = ""; return; }
    const words = msg.text.split(/\s+/);
    el.innerHTML = words.map((w) => `<span class="w">${w}</span>`).join(" ");
    const spans = el.querySelectorAll(".w");
    if (!msg.duration_ms) { spans.forEach((s) => s.classList.add("done")); return; }
    const start = performance.now();
    const per = msg.duration_ms / words.length;
    captionTimer = setInterval(() => {
      const k = Math.floor((performance.now() - start) / per);
      spans.forEach((s, i) => { s.classList.toggle("done", i < k); s.classList.toggle("on", i === k); });
      if (k >= words.length) { clearInterval(captionTimer); captionTimer = null; spans.forEach((s) => { s.classList.add("done"); s.classList.remove("on"); }); }
    }, 40);
  }

  function handle(msg) {
    switch (msg.type) {
      case "chart":
        switch (msg.action) {
          case "load":
            $("#symbol").textContent = msg.symbol || "—"; $("#lg-sym").textContent = msg.symbol || "—"; setTf(msg.tf); curSymbol = msg.symbol || ""; curTf = msg.tf || ""; chart.load(msg);
            $("#lg-src").textContent = /BTC|ETH|SOL|PAXG/.test(msg.symbol || "") ? "Binance" : "Swissquote";
            chart.setWatermark(msg.symbol, msg.tf, $("#lg-src").textContent);
            $("#chart-note").textContent = msg.note || ""; $("#chart-note").style.display = msg.note ? "" : "none";
            room.react("type");
            break;
          case "update": chart.update(msg.candle); break;
          case "prepend": chart.prepend(msg); break;
          case "marker": chart.marker(msg); room.react("type"); break;
          case "highlight": chart.highlight(msg); break;
          case "hline": chart.hline(msg); room.react("type"); break;
          case "trendline": chart.trendline(msg); room.react("type"); break;
          case "zone": chart.zone(msg); room.react("type"); break;
          case "rect": chart.rect(msg); room.react("type"); break;
          case "fib": chart.fib(msg); room.react("type"); break;
          case "path": chart.path(msg); room.react("type"); break;
          case "arrow": chart.arrow(msg); room.react("type"); break;
          case "note": chart.note(msg); room.react("type"); break;
          case "indicator": chart.indicator(msg); break;
          case "vline": chart.vline(msg); break;
          case "channel": chart.channel(msg); room.react("type"); break;
          case "regression": chart.regression(msg); room.react("type"); break;
          case "pitchfork": chart.pitchfork(msg); room.react("type"); break;
          case "fib_ext": chart.fibExt(msg); room.react("type"); break;
          case "fib_fan": chart.fibFan(msg); room.react("type"); break;
          case "position": chart.position(msg); room.react("type"); break;
          case "measure": chart.measure(msg); break;
          case "vprofile": chart.vprofile(msg); break;
          case "avwap": chart.avwap(msg); break;
          case "study": chart.study(msg); break;
          case "pattern": chart.pattern(msg); room.react("type"); break;
          case "alert": chart.alert(msg); break;
          case "session": chart.session(msg); break;
          case "keylevels": chart.keylevels(msg); break;
          case "remove": chart.remove(msg); break;
          case "zoom": chart.zoom(msg); break;
          case "clear": chart.clear(); break;
        }
        break;
      case "caption": caption(msg); break;
      case "mouth": room.setLevel(msg.level || 0); break;
      case "beat": room.react("nod"); break;
      case "react": room.react(msg.kind, msg.side); break;
      case "quote": room.quote(msg); break;
      case "live": {
        const el = $("#live-readout"); el.classList.remove("hidden");
        $("#lr-label").textContent = msg.live ? "LIVE" : "NOW";
        $("#lr-price").textContent = msg.price >= 1000 ? msg.price.toLocaleString("en-US", { maximumFractionDigits: 1 }) : msg.price >= 10 ? msg.price.toFixed(2) : msg.price.toFixed(4);
        const c = $("#lr-chg"); c.textContent = (msg.chg >= 0 ? "+" : "") + msg.chg.toFixed(2) + "%"; c.style.color = msg.chg >= 0 ? "#22c55e" : "#f56565";
        break;
      }
      case "kline": room.kline(msg); break;
      case "lesson":
        $("#lesson-title").textContent = msg.title || "";
        $("#module-chip").textContent = msg.module || "lesson";
        $("#progress").textContent = msg.step && msg.total ? `${msg.step} / ${msg.total}` : "";
        $("#progress-bar i").style.width = msg.step && msg.total ? `${Math.round((msg.step / msg.total) * 100)}%` : "0%";
        if (msg.summary) { $("#summary-card .s-text").textContent = msg.summary; $("#summary-card").classList.remove("hidden"); }
        else $("#summary-card").classList.add("hidden");
        break;
      case "mode":
        $("#mode-chip").textContent = (msg.value || "lesson").toUpperCase();
        if (msg.value === "market") room.react("lean", "center");
        if (msg.value === "q&a") room.react("relax");
        break;
      case "question":
        if (msg.clear) { $("#question-card").classList.add("hidden"); }
        else {
          $("#question-card .q-user").textContent = msg.user && msg.user !== "Chat" && msg.user !== "Quick quiz" ? `${msg.user} asked` : (msg.user || "Question");
          $("#question-card .q-text").textContent = msg.text || "";
          $("#question-card").classList.remove("hidden");
        }
        break;
      case "ticker":
        $("#ticker").innerHTML = (msg.items || []).map((t) => {
          const cls = (t.chg || 0) >= 0 ? "up" : "down";
          const sign = (t.chg || 0) >= 0 ? "+" : "";
          return `<div class="tk"><span class="sym">${t.symbol}</span><span>${t.price}</span><span class="${cls}">${sign}${(t.chg || 0).toFixed(2)}%</span>${t.delayed ? '<span class="dl">delayed</span>' : ''}</div>`;
        }).join("");
        break;
      case "hot": {
        const h = $("#hot"); h.classList.remove("hidden"); h.classList.toggle("down", msg.pct < 0);
        $("#hot-sym").textContent = msg.symbol; $("#hot-pct").textContent = (msg.pct >= 0 ? "+" : "") + msg.pct.toFixed(2) + "%";
        h.style.animation = "none"; void h.offsetWidth; h.style.animation = "";
        $("#stage").classList.add("hot-flash"); setTimeout(() => $("#stage").classList.remove("hot-flash"), 1600);
        clearTimeout(window.__hotT); window.__hotT = setTimeout(() => h.classList.add("hidden"), 6000);
        break;
      }
      case "goal": {
        const g = $("#goal"); g.classList.remove("hidden");
        $("#goal-label").textContent = `Likes ${msg.likes.toLocaleString()} / ${msg.target.toLocaleString()}`;
        g.querySelector(".bar i").style.width = Math.min(100, (msg.likes / msg.target) * 100).toFixed(1) + "%";
        $("#goal-viewers").textContent = msg.viewers ? `${msg.viewers} watching` : "";
        break;
      }
      case "state": {
        $("#btn-pause").classList.toggle("on", !!msg.paused); $("#btn-pause span").textContent = msg.paused ? "Resume" : "Pause";
        $("#btn-mute").classList.toggle("on", !!msg.muted); $("#btn-mute span").textContent = msg.muted ? "Unmute" : "Mute";
        $("#pill-paused").classList.toggle("hidden", !msg.paused); $("#pill-muted").classList.toggle("hidden", !msg.muted);
        break;
      }
      case "disclosure":
        if (msg.text) $("#disclosure").textContent = msg.text;
        break;
    }
  }

  // ?fit=1 scales the fixed 1080x1920 stage to the window (preview only; LIVE Studio captures the real size)
  if (params.has("fit")) {
    const fit = () => {
      const s = Math.min(window.innerWidth / 1080, window.innerHeight / 1920);
      $("#stage").style.transform = `scale(${s})`;
    };
    fit();
    window.addEventListener("resize", fit);
  }

  // every stage-side failure is reported to the hub so it lands in logs/stream.log (that is how a vanished chart gets diagnosed)
  function report(err, ctx) { try { send({ type: "stage_error", text: String(err && err.stack || err).slice(0, 600), ctx: ctx ? String(ctx).slice(0, 160) : "" }); } catch (e) { /* offline */ } }
  window.addEventListener("error", (e) => report(e.error || e.message, "window.onerror"));
  window.addEventListener("unhandledrejection", (e) => report(e.reason, "unhandledrejection"));
  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws/stage`);
    const hello = () => send({ type: "ready", dpr: window.devicePixelRatio, w: window.innerWidth, h: window.innerHeight, ua: navigator.userAgent.slice(-40) });
    ws.onopen = hello;
    let rsT = null; window.addEventListener("resize", () => { clearTimeout(rsT); rsT = setTimeout(hello, 800); });   // the final geometry lands in the log too
    ws.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch (err) { console.error(err); report(err, e.data); } };
    ws.onclose = () => setTimeout(connect, 1000);
  }
  connect();
  window.__stage = { chart, room, handle };
})();
