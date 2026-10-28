/* Real-time 3D trading room (three.js). A rigged human sits at a desk seen from behind,
   posed and animated procedurally: breathing, head tracking the monitors, typing with both
   hands (IK), mouse drift, coffee sips, leaning in on big moves, chair reclining with the
   body, foot taps and weight shifts. Monitors are real screens: live chart canvases become
   emissive textures that also light the room. */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { FBXLoader } from "three/addons/loaders/FBXLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";
import { RectAreaLightHelper } from "three/addons/helpers/RectAreaLightHelper.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const LWC = window.LightweightCharts;
const W = 1080, H = 941;

// ------------------------------------------------------------------ helpers
const lerp = (a, b, t) => a + (b - a) * t;
const damp = (cur, target, lambda, dt) => lerp(cur, target, 1 - Math.exp(-lambda * dt));
const rad = (d) => (d * Math.PI) / 180;
function fmt(p) { return p >= 1000 ? p.toLocaleString("en-US", { maximumFractionDigits: 1 }) : p >= 10 ? p.toFixed(2) : p.toFixed(4); }

function canvasTexture(draw, w, h) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function woodTexture(w = 1024, h = 1024, base = "#6b4a2b") {
  const t = canvasTexture((ctx) => {
    ctx.fillStyle = base; ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 1400; i++) {
      ctx.strokeStyle = `rgba(${20 + Math.random() * 40},${10 + Math.random() * 20},0,${0.05 + Math.random() * 0.12})`;
      ctx.lineWidth = 1 + Math.random() * 3; ctx.beginPath();
      const y = Math.random() * h; ctx.moveTo(0, y); ctx.bezierCurveTo(w / 3, y + (Math.random() - 0.5) * 30, 2 * w / 3, y + (Math.random() - 0.5) * 30, w, y); ctx.stroke();
    }
    for (let x = 0; x < w; x += 128) { ctx.fillStyle = "rgba(0,0,0,.35)"; ctx.fillRect(x, 0, 3, h); }
  }, w, h);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
}
function wallTexture() {
  return canvasTexture((ctx, w, h) => {
    ctx.fillStyle = "#b9a98f"; ctx.fillRect(0, 0, w, h);
    const img = ctx.getImageData(0, 0, w, h); const d = img.data;
    for (let i = 0; i < d.length; i += 4) { const n = (Math.random() - 0.5) * 14; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
    ctx.putImageData(img, 0, 0);
  }, 512, 512);
}
function rugTexture() {
  const t = canvasTexture((ctx, w, h) => {
    ctx.fillStyle = "#3a3f4a"; ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 9000; i++) { ctx.fillStyle = `rgba(${150 + Math.random() * 80},${140 + Math.random() * 70},${120 + Math.random() * 60},${Math.random() * 0.5})`; ctx.fillRect(Math.random() * w, Math.random() * h, 2, 2); }
    ctx.strokeStyle = "rgba(220,200,160,.5)"; ctx.lineWidth = 6; ctx.strokeRect(24, 24, w - 48, h - 48);
  }, 1024, 1024);
  return t;
}

// ------------------------------------------------------------------ screens (chart canvases -> textures)
class Screen {
  constructor(kind, symbol, w, h) {
    this.kind = kind; this.symbol = symbol; this.w = w; this.h = h;
    this.canvas = document.createElement("canvas"); this.canvas.width = w; this.canvas.height = h;
    this.ctx = this.canvas.getContext("2d");
    this.texture = new THREE.CanvasTexture(this.canvas); this.texture.colorSpace = THREE.SRGBColorSpace;
    this.quote = null; this.rows = {}; this.flash = {}; this.lastShot = 0; this.shot = null;
    if (kind === "chart") {
      this.host = document.createElement("div");
      this.host.style.cssText = `position:absolute;left:-5000px;top:0;width:${w}px;height:${h - 40}px;`;
      document.body.appendChild(this.host);
      this.chart = LWC.createChart(this.host, {
        width: w, height: h - 40,
        layout: { background: { type: "solid", color: "#0c1118" }, textColor: "#9aa4b2", fontSize: 13 },
        grid: { vertLines: { color: "#151c26" }, horzLines: { color: "#151c26" } },
        rightPriceScale: { borderColor: "#2a3442", scaleMargins: { top: 0.1, bottom: 0.2 } },
        timeScale: { borderColor: "#2a3442", timeVisible: true, secondsVisible: false, barSpacing: 6, rightOffset: 3 },
        crosshair: { mode: 0, vertLine: { visible: false }, horzLine: { visible: false } },
        handleScroll: false, handleScale: false,
      });
      this.series = this.chart.addSeries(LWC.CandlestickSeries, { upColor: "#26a69a", downColor: "#ef5350", borderVisible: false, wickUpColor: "#26a69a", wickDownColor: "#ef5350" });
      this.ma = this.chart.addSeries(LWC.LineSeries, { color: "#f5c542", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      this.candles = [];
    }
    this.draw();
  }
  setCandles(arr) {
    const ok = (c) => c && [c.open, c.high, c.low, c.close].every((v) => typeof v === "number" && isFinite(v));
    arr = arr.filter(ok).sort((a, b) => a.time - b.time).filter((c, i, a) => i === 0 || c.time > a[i - 1].time);
    this.candles = arr.slice(-140); this.series.setData(this.candles); this._ma(); this.chart.timeScale().scrollToRealTime(); this.lastShot = 0;
  }
  update(c) {
    if (!c || [c.open, c.high, c.low, c.close].some((v) => typeof v !== "number" || !isFinite(v))) return;
    const n = this.candles.length;
    if (n && this.candles[n - 1].time === c.time) this.candles[n - 1] = c;
    else { if (n && c.time < this.candles[n - 1].time) return; this.candles.push(c); if (this.candles.length > 180) this.candles.shift(); }
    try { this.series.update(c); } catch (e) { this.series.setData(this.candles); }
    this._ma(); this.lastShot = 0;
  }
  _ma() {
    const n = 20, out = [];
    for (let i = n - 1; i < this.candles.length; i++) { let s = 0; for (let j = i - n + 1; j <= i; j++) s += this.candles[j].close; out.push({ time: this.candles[i].time, value: s / n }); }
    this.ma.setData(out);
  }
  setQuote(q) {
    if (this.kind === "chart") { if (q.symbol === this.symbol) { this.quote = q; this.lastShot = 0; } return; }
    const prev = this.rows[q.symbol];
    if (prev && prev.price !== q.price) this.flash[q.symbol] = { dir: q.price > prev.price ? 1 : -1, t: performance.now() };
    this.rows[q.symbol] = q; this.lastShot = 0;
  }
  draw(now = performance.now()) {
    if (now - this.lastShot < 150) return;
    this.lastShot = now;
    const ctx = this.ctx, w = this.w, h = this.h;
    ctx.fillStyle = "#0c1118"; ctx.fillRect(0, 0, w, h);
    // title bar
    ctx.fillStyle = "#141b24"; ctx.fillRect(0, 0, w, 40); ctx.fillStyle = "#2a3442"; ctx.fillRect(0, 40, w, 1);
    ctx.font = "bold 20px Segoe UI, sans-serif"; ctx.fillStyle = "#e6edf3"; ctx.textBaseline = "middle";
    if (this.kind === "chart") {
      ctx.fillText(this.symbol, 14, 20);
      if (this.quote) {
        ctx.font = "bold 20px Segoe UI, sans-serif"; ctx.fillStyle = "#fff"; ctx.fillText(fmt(this.quote.price), 150, 20);
        ctx.font = "16px Segoe UI, sans-serif"; ctx.fillStyle = this.quote.chg >= 0 ? "#26a69a" : "#ef5350";
        ctx.fillText((this.quote.chg >= 0 ? "+" : "") + this.quote.chg.toFixed(2) + "%" + (this.quote.delayed ? "  delayed" : ""), 270, 20);
      }
      ctx.font = "14px Segoe UI, sans-serif"; ctx.fillStyle = "#8b949e"; ctx.textAlign = "right"; ctx.fillText("1m  ·  live", w - 12, 20); ctx.textAlign = "left";
      try { const shot = this.chart.takeScreenshot(); ctx.drawImage(shot, 0, 40, w, h - 40); } catch (e) { /* chart not ready */ }
    } else {
      ctx.fillText("Watchlist", 14, 20); ctx.font = "14px Segoe UI, sans-serif"; ctx.fillStyle = "#8b949e"; ctx.textAlign = "right"; ctx.fillText("live", w - 12, 20); ctx.textAlign = "left";
      const syms = ["XAU/USD", "BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "PAXG/USD"];
      let y = 64;
      for (const s of syms) {
        const q = this.rows[s], f = this.flash[s];
        if (f && now - f.t < 900) { ctx.fillStyle = f.dir > 0 ? `rgba(38,166,154,${0.45 * (1 - (now - f.t) / 900)})` : `rgba(239,83,80,${0.45 * (1 - (now - f.t) / 900)})`; ctx.fillRect(0, y - 20, w, 40); }
        ctx.font = "bold 19px Segoe UI, sans-serif"; ctx.fillStyle = "#c9d1d9"; ctx.fillText(s, 14, y);
        ctx.textAlign = "right";
        ctx.font = "19px Segoe UI, sans-serif"; ctx.fillStyle = "#e6edf3"; ctx.fillText(q ? fmt(q.price) : "—", w - 110, y);
        ctx.font = "bold 17px Segoe UI, sans-serif"; ctx.fillStyle = q ? (q.chg >= 0 ? "#26a69a" : "#ef5350") : "#8b949e"; ctx.fillText(q ? (q.chg >= 0 ? "+" : "") + q.chg.toFixed(2) + "%" : "", w - 12, y);
        ctx.textAlign = "left"; ctx.fillStyle = "#151c26"; ctx.fillRect(10, y + 20, w - 20, 1); y += 44;
      }
    }
    this.texture.needsUpdate = true;
  }
  dominantColor() {
    if (this.kind !== "chart" || !this.candles.length) return new THREE.Color(0x6a8fbf);
    const c = this.candles[this.candles.length - 1];
    return c.close >= c.open ? new THREE.Color(0x3fb39f) : new THREE.Color(0xd9655f);
  }
}

// ------------------------------------------------------------------ the trader (procedural rig control)
class Trader {
  constructor(root) {
    this.root = root; this.bones = {};
    // three.js sanitizes node names (dots/spaces removed): "Shoulder.L" arrives as "ShoulderL"
    const ALIAS = { ShoulderL: "LeftShoulder", UpperArmL: "LeftArm", LowerArmL: "LeftForeArm", WristL: "LeftHand", HandL: "LeftHand", UpperLegL: "LeftUpLeg", LowerLegL: "LeftLeg", FootL: "LeftFoot",
      ShoulderR: "RightShoulder", UpperArmR: "RightArm", LowerArmR: "RightForeArm", WristR: "RightHand", HandR: "RightHand", UpperLegR: "RightUpLeg", LowerLegR: "RightLeg", FootR: "RightFoot",
      Abdomen: "Spine", Torso: "Spine1", Chest: "Spine2", spine: "Spine", chest: "Spine2", upperChest: "Spine2", neck: "Neck", head: "Head", hips: "Hips" };
    const fingerRx = /^(Index|Middle|Ring|Pinky|Thumb)(\d)(L|R)$/;
    this.rig = "mixamo";
    root.traverse((o) => {
      if (!o.isBone) return;
      const n = o.name.replace(/^mixamorig[:_]?/i, "").replace(/[.:_\s]/g, "");
      let key = ALIAS[n] || null;
      const fm = n.match(fingerRx);
      if (fm) key = (fm[3] === "L" ? "Left" : "Right") + "Hand" + fm[1] + fm[2];
      if (n === "WristL" || n === "WristR" || n === "Abdomen") this.rig = "quaternius";
      this.bones[key || n] = o;
    });
    this.b = (n) => this.bones[n] || this.bones[n.replace("Left", "L").replace("Right", "R")] || null;
    this.level = 0; this.shown = 0; this.lean = 0; this.leanT = 0; this.leanUntil = 0;
    this.lookX = 0; this.lookY = 0; this.lookTX = 0; this.lookTY = 0; this.lookUntil = 0;
    this.typeUntil = 0; this.nodUntil = 0; this.sip = null; this.sipAt = performance.now() + 25000 + Math.random() * 30000;
    this.fidgetAt = performance.now() + 6000; this.fidget = { hips: 0, tilt: 0, target: { hips: 0, tilt: 0 } };
    this.footTapUntil = 0; this.shoulderL = 0; this.shoulderR = 0;
    this.restPose = {};
    for (const [k, bone] of Object.entries(this.bones)) { this.restPose[k] = bone.quaternion.clone(); bone.userData.rest = bone.quaternion.clone(); }
    this.handTargets = { L: new THREE.Vector3(), R: new THREE.Vector3() };
    this.tmp = { v1: new THREE.Vector3(), v2: new THREE.Vector3(), q: new THREE.Quaternion(), m: new THREE.Matrix4(), w: new THREE.Vector3() };
    this.mug = null; this.mugHome = new THREE.Vector3();
    this.sign = this.rig === "quaternius" ? { spine: 1, shin: -1 } : { spine: -1, shin: -1 };
    this.calibrated = false;
  }
  setLevel(v) { this.level = Math.max(0, Math.min(1, v)); }
  react(kind, side) {
    const now = performance.now();
    const sx = side === "left" ? -0.9 : side === "right" ? 0.9 : 0;
    if (kind === "lean") { this.leanT = 1; this.leanUntil = now + 5000; this.lookTX = sx; this.lookTY = 0.15; this.lookUntil = now + 5000; }
    else if (kind === "relax") { this.leanT = -0.7; this.leanUntil = now + 6000; this.lookTX = 0; this.lookUntil = now + 2000; }
    else if (kind === "type") { this.typeUntil = now + 2200; }
    else if (kind === "nod") { this.nodUntil = now + 600; }
    else if (kind === "look") { this.lookTX = sx; this.lookUntil = now + 3000; }
    else if (kind === "sip") { this.sipAt = now; }
  }
  // rotate `bone` (in its local frame) so that its child-chain effector moves toward target (one CCD step)
  _ccdStep(bone, effector, target, maxAngle) {
    const { v1, v2, q, w } = this.tmp;
    bone.getWorldPosition(w);
    effector.getWorldPosition(v1).sub(w).normalize();
    v2.copy(target).sub(w).normalize();
    let angle = Math.acos(THREE.MathUtils.clamp(v1.dot(v2), -1, 1));
    if (angle < 1e-4) return;
    angle = Math.min(angle, maxAngle);
    const axis = new THREE.Vector3().crossVectors(v1, v2).normalize();
    // bring axis into bone local space
    const parentWorldQuat = new THREE.Quaternion(); bone.parent.getWorldQuaternion(parentWorldQuat);
    axis.applyQuaternion(parentWorldQuat.invert());
    q.setFromAxisAngle(axis, angle);
    bone.quaternion.premultiply(q);
    bone.updateMatrixWorld(true);
  }
  _solveArm(side, target) {
    const arm = this.b(side + "Arm"), fore = this.b(side + "ForeArm"), hand = this.b(side + "Hand");
    if (!arm || !fore || !hand) return;
    for (let i = 0; i < 6; i++) { this._ccdStep(fore, hand, target, 0.35); this._ccdStep(arm, hand, target, 0.25); }
  }
  pose(dt, now, ctx) {
    const t = now / 1000, B = this.b;
    const rest = (n) => { const b = B(n); if (b && b.userData.rest) b.quaternion.copy(b.userData.rest); return b; };
    const rotX = (b, a) => b && b.rotateX(a), rotY = (b, a) => b && b.rotateY(a), rotZ = (b, a) => b && b.rotateZ(a);
    // --- state machines
    this.shown = damp(this.shown, this.level, 14, dt);
    if (now > this.leanUntil) this.leanT = 0;
    this.lean = damp(this.lean, this.leanT, 2.2, dt);
    if (now > this.lookUntil) { this.lookTX = Math.sin(t / 7) * 0.35; this.lookTY = Math.sin(t / 11) * 0.08; }
    this.lookX = damp(this.lookX, this.lookTX, 2.5, dt); this.lookY = damp(this.lookY, this.lookTY, 2.5, dt);
    if (now > this.fidgetAt) { this.fidget.target = { hips: (Math.random() - 0.5) * 0.06, tilt: (Math.random() - 0.5) * 0.08 }; this.fidgetAt = now + 7000 + Math.random() * 14000; if (Math.random() < 0.35) this.footTapUntil = now + 4000 + Math.random() * 5000; }
    this.fidget.hips = damp(this.fidget.hips, this.fidget.target.hips, 1.2, dt); this.fidget.tilt = damp(this.fidget.tilt, this.fidget.target.tilt, 1.2, dt);
    const typing = now < this.typeUntil || (Math.sin(t / 5.3) > 0.55 && !this.sip);     // spontaneous typing bursts too
    const breath = Math.sin(t * 2 * Math.PI / 4.3), breath2 = Math.sin(t * 2 * Math.PI / 4.3 + 0.9);
    const talkBob = this.shown * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI * 2.7));
    const nod = now < this.nodUntil ? Math.sin((this.nodUntil - now) / 600 * Math.PI) : 0;

    // --- base sitting pose (from rest), then layered motion
    const hips = rest("Hips");
    const spine = rest("Spine"), spine1 = rest("Spine1"), spine2 = rest("Spine2"), neck = rest("Neck"), head = rest("Head");
    const lsh = rest("LeftShoulder"), rsh = rest("RightShoulder");
    // arms keep their IK-solved rotations between frames (the solver converges and stays smooth); hands are re-posed each frame
    rest("LeftHand"); rest("RightHand");
    const lul = rest("LeftUpLeg"), rul = rest("RightUpLeg"), ll = rest("LeftLeg"), rl = rest("RightLeg"), lf = rest("LeftFoot"), rf = rest("RightFoot");
    if (hips) { hips.position.z = ctx.hipsRestZ + this.lean * 0.03; hips.position.y = ctx.hipsRestY + breath * 0.002 - Math.abs(this.lean) * 0.004; rotZ(hips, this.fidget.hips); rotX(hips, this.sign.spine * (-rad(3) + this.lean * rad(4))); }
    // legs: thighs forward, shins down
    rotX(lul, rad(84)); rotX(rul, rad(86)); rotZ(lul, rad(-6)); rotZ(rul, rad(6));
    rotX(ll, this.sign.shin * rad(92)); rotX(rl, this.sign.shin * rad(88));
    if (this.rig !== "quaternius") { rotX(lf, rad(-6)); rotX(rf, rad(-4) + (now < this.footTapUntil ? Math.max(0, Math.sin(t * 2 * Math.PI * 2.1)) * rad(10) : 0)); }
    // spine: forward hunch + lean + breathing + weight shift
    const S = this.sign.spine;
    rotX(spine, S * ((rad(7) + this.lean * rad(8)) + breath * rad(0.5))); rotZ(spine, this.fidget.tilt * 0.5);
    rotX(spine1, S * ((rad(6) + this.lean * rad(5)) + breath * rad(0.9)));
    rotX(spine2, S * ((rad(5) + this.lean * rad(4)) + breath2 * rad(0.8))); rotY(spine2, this.lookX * rad(6));
    // shoulders rise with breath, hunch forward when typing/leaning
    rotZ(lsh, breath * rad(0.8) + this.lean * rad(2)); rotZ(rsh, -breath * rad(0.8) - this.lean * rad(2));
    // neck/head: look at monitors, talk bob, nods, fidget tilt
    rotY(neck, this.lookX * rad(14)); rotX(neck, S * (rad(10) - this.lookY * rad(10) + talkBob * rad(2.5) + nod * rad(6)));
    rotY(head, this.lookX * rad(12)); rotX(head, S * (rad(6) - this.lookY * rad(8) + talkBob * rad(2) + nod * rad(5) + this.lean * rad(3))); rotZ(head, this.fidget.tilt + this.shown * Math.sin(t * 2 * Math.PI * 1.3) * rad(1.5));
    this.root.updateMatrixWorld(true);
    if (!this.calibrated && hips) {   // first frame: put the hip joint just above the seat cushion
      const hw = hips.getWorldPosition(this.tmp.w); this.root.position.y += 0.56 - hw.y; this.root.updateMatrixWorld(true); this.calibrated = true;
    }
    if (this.rig === "quaternius") {   // feet are not parented to the legs on this rig: place them under the knees, on the floor
      for (const side of ["Left", "Right"]) {
        const knee = B(side + "Leg"), foot = B(side + "Foot");
        if (!knee || !foot || !foot.parent) continue;
        const kw = knee.getWorldPosition(new THREE.Vector3());
        const target = new THREE.Vector3(kw.x, 0.02, kw.z - 0.06 + (side === "Right" && now < this.footTapUntil ? Math.max(0, Math.sin(t * 2 * Math.PI * 2.1)) * 0.03 : 0));
        foot.position.copy(foot.parent.worldToLocal(target));
      }
      this.root.updateMatrixWorld(true);
    }

    // --- hands via IK: left on keyboard, right on mouse (or typing), sip sequence on the right
    const kb = ctx.keyboard, mouse = ctx.mouse;
    const tl = this.handTargets.L.copy(kb).add(new THREE.Vector3(-0.1, 0.035, 0.04));
    const tr = this.handTargets.R.copy(mouse).add(new THREE.Vector3(0, 0.03, 0));
    if (typing) {
      const f = 7.5;
      tl.x += Math.sin(t * 2 * Math.PI * 1.1) * 0.03; tl.y += Math.abs(Math.sin(t * 2 * Math.PI * f)) * 0.012; tl.z += Math.sin(t * 2 * Math.PI * 0.7) * 0.02;
      tr.copy(kb).add(new THREE.Vector3(0.12, 0.035, 0.02)); tr.x += Math.sin(t * 2 * Math.PI * 0.9 + 1) * 0.03; tr.y += Math.abs(Math.sin(t * 2 * Math.PI * f + 1.3)) * 0.012;
    } else {
      tr.x += Math.sin(t * 2 * Math.PI / 6) * 0.012; tr.z += Math.sin(t * 2 * Math.PI / 4.3) * 0.015; // mouse drifting
      tl.y += breath * 0.002; tl.x += Math.sin(t / 9) * 0.01;
    }
    // sip: reach mug, lift to mouth, hold, return
    if (!this.sip && now > this.sipAt && this.mug && !typing) this.sip = { t0: now };
    if (this.sip) {
      const e = (now - this.sip.t0) / 1000; // phases: 0-1 reach, 1-2.4 lift, 2.4-4 hold, 4-5.4 lower, 5.4-6.2 release
      const mouth = new THREE.Vector3(); (head || neck || hips).getWorldPosition(mouth); mouth.add(new THREE.Vector3(0.04, -0.08, 0.12));
      const home = this.mugHome, hold = new THREE.Vector3();
      if (e < 1) { tr.lerpVectors(tr, home.clone().add(new THREE.Vector3(0, 0.05, 0)), Math.min(1, e)); }
      else if (e < 2.4) { const k = THREE.MathUtils.smoothstep(e, 1, 2.4); hold.lerpVectors(home.clone().add(new THREE.Vector3(0, 0.05, 0)), mouth, k); tr.copy(hold); this.mug.position.copy(hold).sub(new THREE.Vector3(0, 0.05, 0)); this.mug.rotation.x = -k * 0.35; }
      else if (e < 4.0) { tr.copy(mouth).add(new THREE.Vector3(0, Math.sin((e - 2.4) * 3) * 0.004, 0)); this.mug.position.copy(tr).sub(new THREE.Vector3(0, 0.05, 0)); this.mug.rotation.x = -0.35 - Math.sin((e - 2.4) * 2) * 0.1; }
      else if (e < 5.4) { const k = THREE.MathUtils.smoothstep(e, 4.0, 5.4); hold.lerpVectors(mouth, home.clone().add(new THREE.Vector3(0, 0.05, 0)), k); tr.copy(hold); this.mug.position.copy(hold).sub(new THREE.Vector3(0, 0.05, 0)); this.mug.rotation.x = -(1 - k) * 0.35; }
      else if (e < 6.2) { this.mug.position.copy(home); this.mug.rotation.x = 0; tr.lerpVectors(home.clone().add(new THREE.Vector3(0, 0.05, 0)), tr, THREE.MathUtils.smoothstep(e, 5.4, 6.2)); }
      else { this.sip = null; this.sipAt = now + 40000 + Math.random() * 60000; }
    }
    this._solveArm("Left", tl); this._solveArm("Right", tr);
    // hands flat on the desk, fingers curled a little
    const lh = B("LeftHand"), rh = B("RightHand");
    if (lh) { rotX(lh, rad(-10)); rotZ(lh, rad(10)); } if (rh) { rotX(rh, rad(-8)); rotZ(rh, rad(-10)); }
    for (const side of ["Left", "Right"]) for (const f of ["Index", "Middle", "Ring", "Pinky"]) for (let i = 1; i <= 3; i++) {
      const fb = rest(side + "Hand" + f + i); if (fb) rotX(fb, rad(18) + (typing ? Math.abs(Math.sin(t * 2 * Math.PI * 7 + i + f.length)) * rad(12) : 0));
    }
    this.root.updateMatrixWorld(true);
  }
}

// ------------------------------------------------------------------ the room
export class Room3D {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setSize(W, H); this.renderer.setPixelRatio(1);
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 0.95;
    container.appendChild(this.renderer.domElement);
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color(0x0a0806);
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture; this.scene.environmentIntensity = 0.25;
    this.camera = new THREE.PerspectiveCamera(46, W / H, 0.05, 30);
    this.camBase = new THREE.Vector3(0.0, 1.72, 1.62); this.camLook = new THREE.Vector3(0, 1.02, -0.72);
    this.camera.position.copy(this.camBase); this.camera.lookAt(this.camLook);
    RectAreaLightUniformsLib.init();
    this.clock = new THREE.Clock();
    this.screens = {
      left: new Screen("chart", "XAU/USD", 640, 400), center: new Screen("chart", "BTC/USD", 680, 420),
      right: new Screen("chart", "ETH/USD", 640, 400), watch: new Screen("watch", null, 380, 680),
    };
    this.ctx = { keyboard: new THREE.Vector3(0, 0.77, -0.40), mouse: new THREE.Vector3(0.27, 0.77, -0.33), hipsRestY: 0, hipsRestZ: 0 };
    this._build();
    this._loadAvatar();
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 0.32, 0.6, 0.86); this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this.last = performance.now(); this.lastMove = {};
    this.trader = null;
    requestAnimationFrame(() => this._loop());
  }

  _mat(color, rough = 0.8, metal = 0.0, extra = {}) { return new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal, ...extra }); }
  _box(w, h, d, mat, x, y, z, cast = true) { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); m.castShadow = cast; m.receiveShadow = true; this.scene.add(m); return m; }

  _build() {
    const s = this.scene;
    // floor, rug, walls, ceiling
    const wood = woodTexture(); wood.repeat.set(3, 3);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(7, 7), this._mat(0xffffff, 0.75, 0.05, { map: wood })); floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; s.add(floor);
    const rug = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.9), this._mat(0xffffff, 1, 0, { map: rugTexture() })); rug.rotation.x = -Math.PI / 2; rug.position.set(0, 0.004, 0.1); rug.receiveShadow = true; s.add(rug);
    const wallMat = this._mat(0xffffff, 0.95, 0, { map: wallTexture() });
    const back = new THREE.Mesh(new THREE.PlaneGeometry(7, 3), wallMat); back.position.set(0, 1.5, -1.55); back.receiveShadow = true; s.add(back);
    const left = new THREE.Mesh(new THREE.PlaneGeometry(6, 3), wallMat); left.rotation.y = Math.PI / 2; left.position.set(-2.4, 1.5, 0); left.receiveShadow = true; s.add(left);
    const right = new THREE.Mesh(new THREE.PlaneGeometry(6, 3), wallMat); right.rotation.y = -Math.PI / 2; right.position.set(2.4, 1.5, 0); right.receiveShadow = true; s.add(right);
    const skirting = this._box(7, 0.1, 0.02, this._mat(0x2a221b, 0.6), 0, 0.05, -1.54, false);
    // desk
    const deskMat = this._mat(0xffffff, 0.55, 0.05, { map: woodTexture(1024, 512, "#5a3b22") });
    this._box(2.3, 0.035, 0.82, deskMat, 0, 0.74, -0.6);
    for (const x of [-1.05, 1.05]) { this._box(0.06, 0.72, 0.06, this._mat(0x1a1a1a, 0.5, 0.4), x, 0.36, -0.95); this._box(0.06, 0.72, 0.06, this._mat(0x1a1a1a, 0.5, 0.4), x, 0.36, -0.25); this._box(0.06, 0.04, 0.76, this._mat(0x1a1a1a, 0.5, 0.4), x, 0.02, -0.6); }
    // keyboard, mouse, mousepad, notebook, bottle
    this._box(0.44, 0.015, 0.15, this._mat(0x111111, 0.45, 0.2), 0, 0.765, -0.42);
    const keys = new THREE.Mesh(new THREE.PlaneGeometry(0.42, 0.13), this._mat(0x222222, 0.6, 0.1, { emissive: 0x3366ff, emissiveIntensity: 0.25 })); keys.rotation.x = -Math.PI / 2; keys.position.set(0, 0.7735, -0.42); s.add(keys);
    this._box(0.3, 0.004, 0.26, this._mat(0x0d0d0d, 0.9), 0.28, 0.76, -0.36, false);
    const mouse = new THREE.Mesh(new THREE.CapsuleGeometry(0.025, 0.05, 6, 12), this._mat(0x151515, 0.35, 0.3)); mouse.rotation.x = Math.PI / 2; mouse.position.set(0.27, 0.78, -0.33); mouse.castShadow = true; s.add(mouse); this.mouse = mouse;
    this._box(0.22, 0.01, 0.16, this._mat(0xe8e2d2, 0.9), -0.55, 0.765, -0.4);
    const bottle = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.24, 20), this._mat(0x2b3a2f, 0.3, 0.6)); bottle.position.set(0.8, 0.88, -0.75); bottle.castShadow = true; s.add(bottle);
    // mug (held during sips)
    const mug = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.042, 0.038, 0.1, 24), this._mat(0xf2ead8, 0.5)); body.castShadow = true; mug.add(body);
    const handle = new THREE.Mesh(new THREE.TorusGeometry(0.03, 0.007, 10, 20, Math.PI), this._mat(0xf2ead8, 0.5)); handle.rotation.z = -Math.PI / 2; handle.position.set(0.045, 0, 0); mug.add(handle);
    const coffee = new THREE.Mesh(new THREE.CircleGeometry(0.037, 24), this._mat(0x2a1507, 0.2, 0.1)); coffee.rotation.x = -Math.PI / 2; coffee.position.y = 0.045; mug.add(coffee);
    mug.position.set(-0.42, 0.81, -0.5); s.add(mug); this.mug = mug;
    // monitors
    this.monitors = {};
    const mon = (id, w, h, x, y, z, ry, screen) => {
      const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = ry;
      const bezel = new THREE.Mesh(new THREE.BoxGeometry(w + 0.03, h + 0.03, 0.03), this._mat(0x0b0b0b, 0.4, 0.3)); bezel.castShadow = true; g.add(bezel);
      const scr = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: screen.texture, toneMapped: false })); scr.position.z = 0.016; g.add(scr);
      const light = new THREE.RectAreaLight(0x88aaff, 2.2, w, h); light.position.z = 0.02; light.lookAt(0, 0, 1); g.add(light);
      const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, Math.max(0.05, y - 0.76 - h / 2 + 0.02), 12), this._mat(0x111111, 0.5, 0.5)); stand.position.set(0, -h / 2 - (y - 0.76 - h / 2) / 2 + 0.01, -0.02); g.add(stand);
      const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.14, 0.012, 24), this._mat(0x111111, 0.5, 0.5)); foot.position.set(0, -(y - 0.76) + 0.006, -0.02); g.add(foot);
      s.add(g); this.monitors[id] = { group: g, light, screen };
    };
    mon("left", 0.6, 0.345, -0.62, 1.12, -0.86, rad(24), this.screens.left);
    mon("center", 0.62, 0.36, 0, 1.13, -0.95, 0, this.screens.center);
    mon("right", 0.6, 0.345, 0.62, 1.12, -0.86, rad(-24), this.screens.right);
    mon("watch", 0.33, 0.6, 1.12, 1.2, -0.62, rad(-48), this.screens.watch);
    // webcam on the center monitor
    const cam = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.025, 0.03), this._mat(0x151515, 0.4, 0.3)); cam.position.set(0, 1.33, -0.94); s.add(cam);
    const camLed = new THREE.Mesh(new THREE.SphereGeometry(0.004, 8, 8), new THREE.MeshBasicMaterial({ color: 0x33ff66 })); camLed.position.set(0.025, 1.33, -0.925); s.add(camLed); this.camLed = camLed;
    // chair
    const chair = new THREE.Group(); chair.position.set(0, 0, 0.05); s.add(chair); this.chair = chair;
    const cm = this._mat(0x151515, 0.75, 0.05), mesh = this._mat(0x1e1e22, 0.9);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.4, 12), cm); base.position.y = 0.2; chair.add(base);
    for (let i = 0; i < 5; i++) { const a = (i / 5) * Math.PI * 2; const leg = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.025, 0.04), cm); leg.position.set(Math.cos(a) * 0.15, 0.03, Math.sin(a) * 0.15); leg.rotation.y = -a; chair.add(leg); const wheel = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 10), cm); wheel.position.set(Math.cos(a) * 0.29, 0.025, Math.sin(a) * 0.29); chair.add(wheel); }
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.07, 0.5), mesh); seat.position.y = 0.44; seat.castShadow = true; chair.add(seat);
    const backG = new THREE.Group(); backG.position.set(0, 0.46, 0.24); chair.add(backG); this.chairBack = backG;
    const backrest = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.46, 0.05), mesh); backrest.position.set(0, 0.25, 0); backrest.castShadow = true; backG.add(backrest);
    for (const x of [-0.27, 0.27]) { const arm = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, 0.3), cm); arm.position.set(x, 0.68, 0.02); chair.add(arm); const post = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.22, 0.04), cm); post.position.set(x, 0.57, 0.1); chair.add(post); }
    // lamp
    const lampPole = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.5, 10), this._mat(0x222222, 0.4, 0.6)); lampPole.position.set(-0.95, 1.0, -0.85); s.add(lampPole);
    const shade = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.14, 24, 1, true), this._mat(0x1a1a1a, 0.5, 0.3, { side: THREE.DoubleSide })); shade.position.set(-0.86, 1.22, -0.8); shade.rotation.z = -0.5; s.add(shade);
    const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.02, 12, 12), new THREE.MeshStandardMaterial({ color: 0xffd9a0, emissive: 0xffc070, emissiveIntensity: 1.6 })); bulb.position.set(-0.84, 1.17, -0.79); s.add(bulb);
    this.lamp = new THREE.PointLight(0xffb067, 2.4, 4, 1.6); this.lamp.position.set(-0.82, 1.15, -0.76); this.lamp.castShadow = true; this.lamp.shadow.mapSize.set(1024, 1024); this.lamp.shadow.bias = -0.002; s.add(this.lamp);
    // ceiling fill + cool spill from the window side
    const fill = new THREE.HemisphereLight(0x5a6a8a, 0x1a120c, 0.35); s.add(fill);
    const spot = new THREE.SpotLight(0xfff0dd, 6, 8, 0.6, 0.5, 1.2); spot.position.set(0.3, 2.7, 0.6); spot.target.position.set(0, 0.8, -0.4); spot.castShadow = true; spot.shadow.mapSize.set(1024, 1024); s.add(spot); s.add(spot.target);
    // wall clock
    const clockG = new THREE.Group(); clockG.position.set(-1.25, 2.15, -1.53); s.add(clockG); this.clockG = clockG;
    clockG.add(new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.03, 48), this._mat(0x15110d, 0.4, 0.2)).rotateX(Math.PI / 2));
    const face = new THREE.Mesh(new THREE.CircleGeometry(0.155, 48), new THREE.MeshStandardMaterial({ map: canvasTexture((ctx, w, h) => {
      ctx.fillStyle = "#f3ecdc"; ctx.beginPath(); ctx.arc(w / 2, h / 2, w / 2, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#2b2520"; ctx.font = "bold 40px Georgia"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      for (let i = 1; i <= 12; i++) { const a = (i / 12) * Math.PI * 2; ctx.fillText(String(i), w / 2 + Math.sin(a) * 100, h / 2 - Math.cos(a) * 100); }
      for (let i = 0; i < 60; i++) { const a = (i / 60) * Math.PI * 2; ctx.fillRect(w / 2 + Math.sin(a) * 122 - 1, h / 2 - Math.cos(a) * 122 - (i % 5 ? 2 : 5), 2, i % 5 ? 4 : 10); }
    }, 256, 256), roughness: 0.6 })); face.position.z = 0.016; clockG.add(face);
    const hand = (len, wdt, col, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(wdt, len, 0.004), new THREE.MeshStandardMaterial({ color: col, roughness: 0.5 })); m.geometry.translate(0, len / 2 - 0.015, 0); m.position.z = z; clockG.add(m); return m; };
    this.hourHand = hand(0.08, 0.012, 0x1a1612, 0.02); this.minHand = hand(0.12, 0.009, 0x1a1612, 0.024); this.secHand = hand(0.135, 0.004, 0xc0392b, 0.028);
    // shelf + books + plant, picture frame
    this._box(0.9, 0.03, 0.25, deskMat, 1.6, 1.5, -1.4); this._box(0.9, 0.03, 0.25, deskMat, 1.6, 1.0, -1.4);
    for (let i = 0; i < 9; i++) this._box(0.035, 0.18 + Math.random() * 0.08, 0.15, this._mat([0x7a2e2e, 0x2e4a7a, 0x3a6a3a, 0xd0c090, 0x5a3a7a][i % 5], 0.8), 1.25 + i * 0.05, 1.6, -1.42);
    const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.06, 0.12, 16), this._mat(0x8a5a3a, 0.9)); pot.position.set(1.75, 1.08, -1.4); s.add(pot);
    for (let i = 0; i < 14; i++) { const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.05, 8, 8), this._mat(0x2f6f3a, 0.9)); leaf.scale.set(1, 0.4, 1.6); leaf.position.set(1.75 + (Math.random() - 0.5) * 0.3, 1.16 + Math.random() * 0.2, -1.4 + (Math.random() - 0.5) * 0.25); leaf.rotation.set(Math.random(), Math.random() * 3, Math.random()); s.add(leaf); }
    const frame = this._box(0.5, 0.36, 0.02, this._mat(0x101010, 0.5, 0.2), 0.9, 2.05, -1.53, false);
    const pic = new THREE.Mesh(new THREE.PlaneGeometry(0.44, 0.3), this._mat(0xffffff, 0.9, 0, { map: canvasTexture((ctx, w, h) => { const g = ctx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#f7b267"); g.addColorStop(0.5, "#f4845f"); g.addColorStop(1, "#2d3047"); ctx.fillStyle = g; ctx.fillRect(0, 0, w, h); ctx.fillStyle = "#1a1a2e"; for (let i = 0; i < 12; i++) ctx.fillRect(i * (w / 12), h * 0.55 + Math.random() * h * 0.2, w / 14, h); }, 256, 180) })); pic.position.set(0.9, 2.05, -1.515); s.add(pic);
    // steam particles above the mug
    const sg = new THREE.BufferGeometry(); const n = 40; const pos = new Float32Array(n * 3); const life = new Float32Array(n);
    for (let i = 0; i < n; i++) { life[i] = Math.random(); pos[i * 3] = 0; pos[i * 3 + 1] = 0; pos[i * 3 + 2] = 0; }
    sg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.steam = new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xfff2e0, size: 0.03, transparent: true, opacity: 0.18, depthWrite: false })); this.steamLife = life; s.add(this.steam);
  }

  _loadAvatar() {
    const loader = new GLTFLoader();
    const draco = new DRACOLoader(); draco.setDecoderPath("/stage/static/vendor/three/examples/jsm/libs/draco/"); loader.setDRACOLoader(draco);
    const fbx = new FBXLoader();
    const base = "/stage/static/assets/room/";
    const candidates = ["avatar.glb", "avatar.fbx", "hoodie.glb", "soldier.glb", "xbot.glb"].map((f) => base + f);
    const tryNext = (i) => {
      if (i >= candidates.length) { console.warn("no avatar found"); return; }
      const url = candidates[i];
      const ok = (obj) => { console.log("avatar loaded:", url); this._placeAvatar({ scene: obj.scene || obj }); };
      const fail = () => tryNext(i + 1);
      if (url.endsWith(".fbx")) fbx.load(url, ok, undefined, fail); else loader.load(url, ok, undefined, fail);
    };
    tryNext(0);
  }
  _placeAvatar(gltf) {
    const model = gltf.scene;
    model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; o.frustumCulled = false; if (o.material && o.material.map) o.material.map.colorSpace = THREE.SRGBColorSpace; } });
    // normalize height to ~1.75 m
    const box = new THREE.Box3().setFromObject(model); const hgt = box.max.y - box.min.y; const k = 1.95 / hgt; model.scale.setScalar(k);
    model.position.set(0, 0, 0.1); model.rotation.y = Math.PI; // facing the monitors (away from camera)
    this.scene.add(model);
    const trader = new Trader(model);
    const hips = trader.b("Hips");
    if (hips) {
      // sit: hips at seat height. Compute hips world y after scale and shift the model down accordingly.
      model.updateMatrixWorld(true);
      const hw = new THREE.Vector3(); hips.getWorldPosition(hw);
      model.position.y += 0.56 - hw.y;   // hip joint a little above the seat cushion (0.475)
      model.position.z = 0.14;
      this.ctx.hipsRestY = hips.position.y; this.ctx.hipsRestZ = hips.position.z;
    }
    trader.mug = this.mug; trader.mugHome.copy(this.mug.position);
    this.trader = trader;
  }

  // ---- public API (same as the 2D room) ----
  quote(q) {
    for (const sc of Object.values(this.screens)) sc.setQuote(q);
    const now = Date.now();
    const rec = this.lastMove[q.symbol] || (this.lastMove[q.symbol] = { t: now, p: q.price });
    if (now - rec.t > 45000) {
      const move = (q.price / rec.p - 1) * 100;
      if (Math.abs(move) > 0.12 && (q.symbol === "XAU/USD" || q.symbol === "BTC/USD") && this.trader) this.trader.react("lean", q.symbol === "XAU/USD" ? "left" : "center");
      rec.t = now; rec.p = q.price;
    }
  }
  kline(msg) { for (const sc of Object.values(this.screens)) if (sc.symbol === msg.symbol) (msg.candles ? sc.setCandles(msg.candles) : sc.update(msg.candle)); }
  setLevel(v) { if (this.trader) this.trader.setLevel(v); }
  react(kind, side) { if (this.trader) this.trader.react(kind, side); }

  _loop() {
    const now = performance.now(); const dt = Math.min(0.05, (now - this.last) / 1000); this.last = now; const t = now / 1000;
    // screens
    for (const sc of Object.values(this.screens)) sc.draw(now);
    for (const m of Object.values(this.monitors)) { const c = m.screen.dominantColor(); m.light.color.lerp(c, 0.05); }
    // clock
    const d = new Date(); const sec = d.getSeconds() + d.getMilliseconds() / 1000, min = d.getMinutes() + sec / 60, hr = (d.getHours() % 12) + min / 60;
    this.secHand.rotation.z = -sec * Math.PI / 30; this.minHand.rotation.z = -min * Math.PI / 30; this.hourHand.rotation.z = -hr * Math.PI / 6;
    // lamp flicker, webcam led blink
    this.lamp.intensity = 2.4 + Math.sin(t * 13.7) * 0.06 + Math.sin(t * 2.3) * 0.09 + (Math.random() - 0.5) * 0.05;
    this.camLed.material.color.setHex(Math.floor(t * 1.5) % 2 ? 0x33ff66 : 0x1a8a3a);
    // steam
    const pos = this.steam.geometry.attributes.position; const home = this.mug.position;
    for (let i = 0; i < this.steamLife.length; i++) {
      this.steamLife[i] += dt * 0.35; if (this.steamLife[i] > 1) this.steamLife[i] = 0;
      const l = this.steamLife[i];
      pos.setXYZ(i, home.x + Math.sin(l * 9 + i) * 0.012 * l, home.y + 0.06 + l * 0.14, home.z + Math.cos(l * 7 + i) * 0.012 * l);
    }
    pos.needsUpdate = true; this.steam.material.opacity = 0.16 * (this.trader && this.trader.sip ? 0.3 : 1);
    // trader + chair (chair reclines/leans with the body)
    if (this.trader) {
      this.trader.pose(dt, now, this.ctx);
      const lean = this.trader.lean;
      this.chairBack.rotation.x = damp(this.chairBack.rotation.x, lean < 0 ? -0.09 * -lean : 0.02 * lean, 3, dt);
      this.chair.rotation.z = damp(this.chair.rotation.z, this.trader.fidget.hips * 0.3, 2, dt);
    }
    // camera: slow handheld drift
    this.camera.position.set(this.camBase.x + Math.sin(t / 6.1) * 0.012, this.camBase.y + Math.sin(t / 7.7) * 0.008, this.camBase.z + Math.sin(t / 9.3) * 0.01);
    this.camera.lookAt(this.camLook.x + Math.sin(t / 8.3) * 0.015, this.camLook.y + Math.sin(t / 5.9) * 0.01, this.camLook.z);
    this.composer.render();
    requestAnimationFrame(() => this._loop());
  }
}
