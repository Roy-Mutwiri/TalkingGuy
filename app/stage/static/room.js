/* The trading room: a photo set with live layers on top.
   - four monitors get real charts/watchlist mapped onto their screens (perspective)
   - a real clock on the wall
   - the trader (cut-out layer) breathes, sways, bobs when talking, types, leans in on big moves
   - coffee steam, lamp flicker, monitor glow on his back
   Coordinates are in room pixels (1080x941 crop of the source photo). */
(function () {
  const LWC = window.LightweightCharts;

  // ---------- geometry helpers: map a rectangle onto an arbitrary quad with CSS matrix3d ----------
  function solve(a, b) { // gaussian elimination, a: 8x8, b: 8
    const n = 8;
    for (let i = 0; i < n; i++) {
      let max = i;
      for (let r = i + 1; r < n; r++) if (Math.abs(a[r][i]) > Math.abs(a[max][i])) max = r;
      [a[i], a[max]] = [a[max], a[i]]; [b[i], b[max]] = [b[max], b[i]];
      for (let r = i + 1; r < n; r++) {
        const f = a[r][i] / a[i][i];
        for (let c = i; c < n; c++) a[r][c] -= f * a[i][c];
        b[r] -= f * b[i];
      }
    }
    const x = new Array(n).fill(0);
    for (let i = n - 1; i >= 0; i--) {
      let s = b[i];
      for (let c = i + 1; c < n; c++) s -= a[i][c] * x[c];
      x[i] = s / a[i][i];
    }
    return x;
  }
  function quadTransform(w, h, q) { // q = [[x,y] TL, TR, BR, BL] destination
    const src = [[0, 0], [w, 0], [w, h], [0, h]];
    const A = [], B = [];
    for (let i = 0; i < 4; i++) {
      const [x, y] = src[i], [u, v] = q[i];
      A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.push(u);
      A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); B.push(v);
    }
    const t = solve(A, B);
    const m = [t[0], t[3], 0, t[6], t[1], t[4], 0, t[7], 0, 0, 1, 0, t[2], t[5], 0, 1];
    return `matrix3d(${m.map((v) => v.toFixed(6)).join(",")})`;
  }

  // ---------- monitors ----------
  const MONITORS = {
    left:   { quad: [[162, 142], [412, 147], [412, 340], [160, 342]], w: 500, h: 390, symbol: "XAU/USD", kind: "chart" },
    center: { quad: [[430, 145], [700, 145], [700, 320], [427, 320]], w: 540, h: 350, symbol: "BTC/USD", kind: "chart" },
    right:  { quad: [[710, 149], [940, 140], [940, 330], [710, 322]], w: 460, h: 370, symbol: "ETH/USD", kind: "chart" },
    watch:  { quad: [[947, 82], [1120, 75], [1120, 405], [950, 390]], w: 350, h: 650, kind: "watch" },
  };
  const WATCHLIST = ["XAU/USD", "BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "PAXG/USD"];

  class Monitor {
    constructor(root, id, cfg) {
      this.cfg = cfg;
      this.el = document.createElement("div");
      this.el.className = "monitor " + cfg.kind;
      this.el.style.width = cfg.w + "px"; this.el.style.height = cfg.h + "px";
      this.el.style.transform = quadTransform(cfg.w, cfg.h, cfg.quad);
      root.appendChild(this.el);
      if (cfg.kind === "chart") this._chart(); else this._watch();
    }
    _chart() {
      this.el.innerHTML = `<div class="mon-bar"><span class="mon-sym">${this.cfg.symbol}</span><span class="mon-price">—</span><span class="mon-chg"></span><span class="mon-tf">1m</span></div><div class="mon-chart"></div>`;
      const host = this.el.querySelector(".mon-chart");
      this.chart = LWC.createChart(host, {
        width: this.cfg.w, height: this.cfg.h - 34,
        layout: { background: { type: "solid", color: "#131722" }, textColor: "#787b86", fontSize: 11 },
        grid: { vertLines: { color: "#1e222d" }, horzLines: { color: "#1e222d" } },
        rightPriceScale: { borderColor: "#30363d", scaleMargins: { top: 0.1, bottom: 0.2 } },
        timeScale: { borderColor: "#30363d", timeVisible: true, secondsVisible: false, barSpacing: 5, rightOffset: 3 },
        crosshair: { mode: 0, vertLine: { visible: false }, horzLine: { visible: false } },
        handleScroll: false, handleScale: false,
      });
      this.series = this.chart.addSeries(LWC.CandlestickSeries, { upColor: "#089981", downColor: "#f23645", borderVisible: false, wickUpColor: "#089981", wickDownColor: "#f23645" });
      this.ma = this.chart.addSeries(LWC.LineSeries, { color: "#f5c542", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      this.candles = [];
    }
    _watch() {
      this.el.innerHTML = `<div class="mon-bar"><span class="mon-sym">Watchlist</span><span class="mon-tf">live</span></div><div class="watch-rows">` +
        WATCHLIST.map((s) => `<div class="wrow" data-s="${s}"><span class="ws">${s}</span><span class="wp">—</span><span class="wc"></span></div>`).join("") + `</div>`;
    }
    setCandles(arr) {
      const ok = (c) => c && [c.open, c.high, c.low, c.close].every((v) => typeof v === "number" && isFinite(v));
      arr = arr.filter(ok).sort((a, b) => a.time - b.time).filter((c, i, a) => i === 0 || c.time > a[i - 1].time);
      this.candles = arr.slice(-120);
      this.series.setData(this.candles);
      this._ma();
      this.chart.timeScale().scrollToRealTime();
    }
    update(c) {
      if (!c || [c.open, c.high, c.low, c.close].some((v) => typeof v !== "number" || !isFinite(v))) return;
      const n = this.candles.length;
      if (n && this.candles[n - 1].time === c.time) this.candles[n - 1] = c;
      else { if (n && c.time < this.candles[n - 1].time) return; this.candles.push(c); if (this.candles.length > 160) this.candles.shift(); }
      try { this.series.update(c); } catch (e) { this.series.setData(this.candles); }
      this._ma();
    }
    _ma() {
      const n = 20, out = [];
      for (let i = n - 1; i < this.candles.length; i++) {
        let s = 0; for (let j = i - n + 1; j <= i; j++) s += this.candles[j].close;
        out.push({ time: this.candles[i].time, value: s / n });
      }
      this.ma.setData(out);
    }
    quote(q) {
      if (this.cfg.kind === "chart") {
        if (q.symbol !== this.cfg.symbol) return;
        this.el.querySelector(".mon-price").textContent = fmt(q.price);
        const c = this.el.querySelector(".mon-chg");
        c.textContent = (q.chg >= 0 ? "+" : "") + q.chg.toFixed(2) + "%" + (q.delayed ? " (delayed)" : "");
        c.className = "mon-chg " + (q.chg >= 0 ? "up" : "down");
      } else {
        const row = this.el.querySelector(`.wrow[data-s="${q.symbol}"]`);
        if (!row) return;
        const p = row.querySelector(".wp"), prev = parseFloat(p.dataset.v || "0");
        p.textContent = fmt(q.price); p.dataset.v = q.price;
        const c = row.querySelector(".wc");
        c.textContent = (q.chg >= 0 ? "+" : "") + q.chg.toFixed(2) + "%";
        c.className = "wc " + (q.chg >= 0 ? "up" : "down");
        if (prev && q.price !== prev) { row.classList.remove("flash-up", "flash-down"); void row.offsetWidth; row.classList.add(q.price > prev ? "flash-up" : "flash-down"); }
      }
    }
  }
  function fmt(p) { return p >= 1000 ? p.toLocaleString("en-US", { maximumFractionDigits: 1 }) : p >= 10 ? p.toFixed(2) : p.toFixed(4); }

  // ---------- clock ----------
  class WallClock {
    constructor(root, cx, cy, r) {
      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      svg.setAttribute("viewBox", "-100 -100 200 200");
      svg.style.cssText = `position:absolute;left:${cx - r}px;top:${cy - r}px;width:${r * 2}px;height:${r * 2}px;`;
      let s = `<defs><radialGradient id="cf" cx="40%" cy="35%" r="70%"><stop offset="0" stop-color="#fff7e8"/><stop offset="1" stop-color="#d9cdb8"/></radialGradient></defs>`;
      s += `<circle r="98" fill="#1a1612"/><circle r="92" fill="url(#cf)"/>`;
      for (let i = 0; i < 60; i++) {
        const a = (i / 60) * Math.PI * 2, big = i % 5 === 0;
        const r1 = big ? 78 : 84, x1 = Math.sin(a) * r1, y1 = -Math.cos(a) * r1, x2 = Math.sin(a) * 88, y2 = -Math.cos(a) * 88;
        s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#2b2520" stroke-width="${big ? 3 : 1}"/>`;
      }
      for (let h = 1; h <= 12; h++) {
        const a = (h / 12) * Math.PI * 2, x = Math.sin(a) * 64, y = -Math.cos(a) * 64 + 7;
        s += `<text x="${x}" y="${y}" text-anchor="middle" font-size="20" font-family="Georgia, serif" fill="#2b2520">${h}</text>`;
      }
      s += `<line id="hh" x1="0" y1="8" x2="0" y2="-48" stroke="#1a1612" stroke-width="6" stroke-linecap="round"/>`;
      s += `<line id="mh" x1="0" y1="10" x2="0" y2="-72" stroke="#1a1612" stroke-width="4" stroke-linecap="round"/>`;
      s += `<line id="sh" x1="0" y1="14" x2="0" y2="-80" stroke="#c0392b" stroke-width="1.6" stroke-linecap="round"/>`;
      s += `<circle r="4" fill="#c0392b"/><circle r="96" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="4"/>`;
      s += `<ellipse cx="-30" cy="-45" rx="40" ry="22" fill="rgba(255,255,255,.08)"/>`;
      svg.innerHTML = s;
      root.appendChild(svg);
      this.hh = svg.querySelector("#hh"); this.mh = svg.querySelector("#mh"); this.sh = svg.querySelector("#sh");
    }
    tick() {
      const d = new Date();
      const ms = d.getMilliseconds(), s = d.getSeconds() + ms / 1000, m = d.getMinutes() + s / 60, h = (d.getHours() % 12) + m / 60;
      this.sh.setAttribute("transform", `rotate(${s * 6})`);
      this.mh.setAttribute("transform", `rotate(${m * 6})`);
      this.hh.setAttribute("transform", `rotate(${h * 30})`);
    }
  }

  // ---------- steam ----------
  class Steam {
    constructor(canvas, x, y) { this.c = canvas; this.ctx = canvas.getContext("2d"); this.x = x; this.y = y; this.p = []; }
    tick(dt) {
      if (Math.random() < 0.35) this.p.push({ x: this.x + (Math.random() - 0.5) * 18, y: this.y, vx: (Math.random() - 0.5) * 6, vy: -18 - Math.random() * 14, r: 4 + Math.random() * 6, a: 0.22 + Math.random() * 0.15, t: 0 });
      const ctx = this.ctx; ctx.clearRect(0, 0, this.c.width, this.c.height);
      this.p = this.p.filter((q) => q.a > 0.01);
      for (const q of this.p) {
        q.t += dt; q.x += (q.vx + Math.sin(q.t * 2.5 + q.r) * 6) * dt; q.y += q.vy * dt; q.r += 9 * dt; q.a -= 0.07 * dt;
        const g = ctx.createRadialGradient(q.x, q.y, 0, q.x, q.y, q.r);
        g.addColorStop(0, `rgba(255,245,230,${q.a})`); g.addColorStop(1, "rgba(255,245,230,0)");
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(q.x, q.y, q.r, 0, Math.PI * 2); ctx.fill();
      }
    }
  }

  // ---------- the trader ----------
  class Trader {
    constructor(person, hand) {
      this.person = person; this.hand = hand;
      this.level = 0; this.shown = 0;
      this.lean = 0; this.leanTarget = 0; this.leanUntil = 0;
      this.typeUntil = 0; this.nodUntil = 0; this.turn = 0; this.turnTarget = 0; this.gestureUntil = 0; this.nodLen = 600; this.nodBobs = 1;
      this.t0 = performance.now();
    }
    setLevel(v) { this.level = Math.max(0, Math.min(1, v)); }
    react(kind, side) {
      const now = performance.now();
      if (kind === "lean") { this.leanTarget = 1; this.leanUntil = now + 4000; this.turnTarget = side === "left" ? -1 : side === "right" ? 1 : 0; }
      else if (kind === "relax") { this.leanTarget = -0.6; this.leanUntil = now + 5000; this.turnTarget = 0; }
      else if (kind === "type") { this.typeUntil = now + 1800; }
      else if (kind === "nod") { this.nodUntil = now + 600; }
      else if (kind === "look") { this.turnTarget = side === "left" ? -1 : side === "right" ? 1 : 0; this.leanUntil = now + 2500; }
      else if (kind === "glance") { this.turnTarget = side === "left" ? -0.8 : side === "right" ? 0.8 : 0; this.leanUntil = now + 1600; this.leanTarget = 0.25; }
      else if (kind === "gesture") { this.gestureUntil = now + 900; }
      else if (kind === "celebrate") { this.nodLen = 1300; this.nodBobs = 2; this.nodUntil = now + 1300; this.leanTarget = 0.6; this.leanUntil = now + 2200; this.gestureUntil = now + 700; }
      else if (kind === "hype") { this.nodLen = 1100; this.nodBobs = 2; this.nodUntil = now + 1100; this.leanTarget = 0.9; this.leanUntil = now + 3000; this.gestureUntil = now + 800; this.turnTarget = 0.2; }
      else if (kind === "attentive") { this.leanTarget = 0.7; this.leanUntil = now + 20000; this.turnTarget = 0.3; }
      else if (kind === "considerate") { this.leanTarget = 0.35; this.leanUntil = now + 8000; this.turnTarget = 0; this.nodLen = 900; this.nodBobs = 1; this.nodUntil = now + 900; }
    }
    tick() {
      const now = performance.now(), t = (now - this.t0) / 1000;
      this.shown += (this.level - this.shown) * 0.35;
      if (now > this.leanUntil) { this.leanTarget = 0; this.turnTarget = 0; }
      this.lean += (this.leanTarget - this.lean) * 0.04;
      this.turn += (this.turnTarget - this.turn) * 0.05;
      const breath = Math.sin(t * 2 * Math.PI / 4.2);                 // 4.2 s breathing cycle
      const sway = Math.sin(t * 2 * Math.PI / 9) * 1.2 + Math.sin(t * 2 * Math.PI / 23) * 0.8;
      const talk = this.shown * (2 + Math.sin(t * 2 * Math.PI * 3.1) * 1.5);  // head bob while speaking
      const nod = now < this.nodUntil ? Math.sin((this.nodUntil - now) / this.nodLen * Math.PI * this.nodBobs) * 5 : 0;
      if (now >= this.nodUntil) { this.nodLen = 600; this.nodBobs = 1; }
      const typing = now < this.typeUntil;
      const typeJ = typing ? Math.sin(t * 2 * Math.PI * 7) * 1.2 : 0;
      const sy = 1 + breath * 0.006 + this.lean * 0.018;
      const sx = 1 + breath * 0.002 + this.lean * 0.012;
      const ty = breath * 1.2 + this.lean * 7 + talk + nod + typeJ * 0.3;
      const tx = sway * 0.9 + this.turn * 6;
      const rot = sway * 0.12 + this.turn * 0.6;
      this.person.style.transform = `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) rotate(${rot.toFixed(3)}deg) scale(${sx.toFixed(4)}, ${sy.toFixed(4)})`;
      const hx = typing ? Math.sin(t * 2 * Math.PI * 4.5) * 2 : Math.sin(t * 2 * Math.PI / 7) * 1.0;
      const gest = now < this.gestureUntil ? Math.sin((this.gestureUntil - now) / 900 * Math.PI) * -6 : 0;   // hand lifts for a beat
      const hy = (typing ? Math.abs(Math.sin(t * 2 * Math.PI * 9)) * -1.0 : breath * 0.4) + gest;
      this.hand.style.transform = `translate(${hx.toFixed(2)}px, ${hy.toFixed(2)}px)`;
    }
  }

  class Room {
    constructor(root) {
      this.root = root;
      // the room goes in front of the overlays already in #room (goal, hot move); never wipe them
      root.insertAdjacentHTML("afterbegin", `<div class="cam">
        <img class="layer bg" src="/stage/static/assets/room/room.png">
        <div class="layer monitors"></div>
        <div class="layer glow"></div>
        <img class="layer person" src="/stage/static/assets/room/person.png" onerror="this.style.display='none'">
        <img class="layer hand" src="/stage/static/assets/room/hand.png">
        <canvas class="layer steam" width="1080" height="941"></canvas>
        <div class="layer lamp"></div>
        <div class="layer vignette"></div></div>`);
      const monRoot = root.querySelector(".monitors");
      this.monitors = {};
      for (const [id, cfg] of Object.entries(MONITORS)) this.monitors[id] = new Monitor(monRoot, id, cfg);
      this.clock = new WallClock(root, 73, 89, 82);
      this.steam = new Steam(root.querySelector(".steam"), 196, 418);
      this.trader = new Trader(root.querySelector(".person"), root.querySelector(".hand"));
      this.trader.cam = root.querySelector(".cam");
      this.lamp = root.querySelector(".lamp"); this.glow = root.querySelector(".glow");
      this.lastPrice = {}; this.lastMoveCheck = {};
      this.last = performance.now();
      const loop = () => {
        const now = performance.now(), dt = Math.min(0.05, (now - this.last) / 1000); this.last = now;
        this.clock.tick(); this.steam.tick(dt); this.trader.tick();
        const t = now / 1000;
        this.lamp.style.opacity = (0.86 + Math.sin(t * 13.7) * 0.03 + Math.sin(t * 2.3) * 0.04 + (Math.random() - 0.5) * 0.02).toFixed(3);
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    }
    quote(q) {
      for (const m of Object.values(this.monitors)) m.quote(q);
      // reaction to a sharp move: compare with the price ~45 s ago
      const now = Date.now();
      const rec = this.lastMoveCheck[q.symbol] || (this.lastMoveCheck[q.symbol] = { t: now, p: q.price });
      if (now - rec.t > 45000) {
        const move = (q.price / rec.p - 1) * 100;
        if (Math.abs(move) > 0.12 && (q.symbol === "XAU/USD" || q.symbol === "BTC/USD")) {
          this.trader.react("lean", q.symbol === "XAU/USD" ? "left" : "center");
          this.glow.style.background = move > 0 ? "radial-gradient(ellipse at 50% 30%, rgba(38,166,154,.22), transparent 60%)" : "radial-gradient(ellipse at 50% 30%, rgba(239,83,80,.22), transparent 60%)";
        }
        rec.t = now; rec.p = q.price;
      }
    }
    kline(msg) {
      for (const m of Object.values(this.monitors)) if (m.cfg.symbol === msg.symbol) (msg.candles ? m.setCandles(msg.candles) : m.update(msg.candle));
    }
    setLevel(v) { this.trader.setLevel(v); }
    react(kind, side) { this.trader.react(kind, side); }
  }

  window.Room = Room;
})();
