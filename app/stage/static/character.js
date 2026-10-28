/* PNGTuber-style character. Uses layered PNGs from /stage/static/assets/character/ when present
   (body.png, eyes_open.png, eyes_closed.png, mouth_0.png, mouth_1.png, mouth_2.png),
   otherwise an inline SVG mascot. Mouth openness follows the TTS amplitude. */
(function () {
  const SVG = [
    '<svg viewBox="0 0 420 480" xmlns="http://www.w3.org/2000/svg">',
    '<defs>',
    '<linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b3a67"/><stop offset="1" stop-color="#1b2544"/></linearGradient>',
    '<linearGradient id="g2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd27a"/><stop offset="1" stop-color="#f5a623"/></linearGradient>',
    '</defs>',
    '<g id="body">',
    '<path d="M90 470 Q90 330 210 330 Q330 330 330 470 Z" fill="url(#g1)"/>',
    '<rect x="150" y="320" width="120" height="40" rx="12" fill="#1b2544"/>',
    '<path d="M160 360 L210 420 L260 360" fill="#f5c542"/>',
    '</g>',
    '<g id="head">',
    '<circle cx="210" cy="190" r="140" fill="url(#g2)"/>',
    '<circle cx="210" cy="190" r="140" fill="none" stroke="#c97d10" stroke-width="6"/>',
    '<ellipse cx="150" cy="175" rx="22" ry="26" fill="#1b2544"/>',
    '<ellipse cx="270" cy="175" rx="22" ry="26" fill="#1b2544"/>',
    '<circle cx="158" cy="168" r="8" fill="#fff"/><circle cx="278" cy="168" r="8" fill="#fff"/>',
    '<g id="lids"><rect id="lidL" x="124" y="140" width="52" height="0" fill="#f5a623"/><rect id="lidR" x="244" y="140" width="52" height="0" fill="#f5a623"/></g>',
    '<path d="M120 120 Q150 100 180 118" stroke="#c97d10" stroke-width="8" fill="none" stroke-linecap="round"/>',
    '<path d="M240 118 Q270 100 300 120" stroke="#c97d10" stroke-width="8" fill="none" stroke-linecap="round"/>',
    '<ellipse id="mouth" cx="210" cy="255" rx="40" ry="8" fill="#5a2a0c"/>',
    '<ellipse id="tongue" cx="210" cy="262" rx="18" ry="4" fill="#e0616b"/>',
    '<rect x="150" y="40" width="120" height="30" rx="15" fill="#1b2544"/>',
    '<circle cx="210" cy="30" r="16" fill="#f56565"><animate attributeName="opacity" values="1;.3;1" dur="1.6s" repeatCount="indefinite"/></circle>',
    '</g>',
    '</svg>',
  ].join("");

  class Character {
    constructor(el) {
      this.el = el;
      this.level = 0;   // target mouth openness 0..1
      this.shown = 0;   // smoothed value actually drawn
      this.blinkUntil = 0;
      this.nextBlink = performance.now() + 2000;
      this.nodUntil = 0;
      this.mode = "svg";
      this._tryPng().then((ok) => { if (!ok) this._svg(); this._loop(); });
    }

    async _tryPng() {
      const base = "/stage/static/assets/character/";
      const names = ["body", "eyes_open", "eyes_closed", "mouth_0", "mouth_1", "mouth_2"];
      try {
        const r = await fetch(base + "body.png", { method: "HEAD" });
        if (!r.ok) return false;
      } catch (e) {
        return false;
      }
      this.el.innerHTML = names.map((n) => '<img data-l="' + n + '" src="' + base + n + '.png">').join("");
      this.layers = {};
      this.el.querySelectorAll("img").forEach((i) => { this.layers[i.dataset.l] = i; });
      this.mode = "png";
      return true;
    }

    _svg() {
      this.el.innerHTML = SVG;
      this.mouth = this.el.querySelector("#mouth");
      this.tongue = this.el.querySelector("#tongue");
      this.lidL = this.el.querySelector("#lidL");
      this.lidR = this.el.querySelector("#lidR");
      this.head = this.el.querySelector("#head");
    }

    setLevel(v) { this.level = Math.max(0, Math.min(1, v)); }
    nod() { this.nodUntil = performance.now() + 500; }

    _loop() {
      const now = performance.now();
      this.shown += (this.level - this.shown) * 0.45;
      if (now > this.nextBlink) {
        this.blinkUntil = now + 120;
        this.nextBlink = now + 2500 + Math.random() * 3500;
      }
      const blinking = now < this.blinkUntil;
      const sway = Math.sin(now / 1400) * 1.6;
      const bob = Math.sin(now / 900) * 4;
      const nod = now < this.nodUntil ? Math.sin(((this.nodUntil - now) / 500) * Math.PI) * 10 : 0;
      this.el.style.transform = "rotate(" + sway + "deg) translateY(" + (bob + nod) + "px)";
      if (this.mode === "svg" && this.mouth) {
        const ry = 8 + this.shown * 26;
        this.mouth.setAttribute("ry", ry.toFixed(1));
        this.tongue.setAttribute("cy", (255 + ry * 0.6).toFixed(1));
        this.tongue.setAttribute("ry", (2 + this.shown * 8).toFixed(1));
        this.lidL.setAttribute("height", blinking ? 56 : 0);
        this.lidR.setAttribute("height", blinking ? 56 : 0);
        this.head.style.transform = "translateY(" + (-this.shown * 3) + "px)";
      } else if (this.mode === "png") {
        const m = this.shown < 0.15 ? "mouth_0" : this.shown < 0.5 ? "mouth_1" : "mouth_2";
        for (const k of ["mouth_0", "mouth_1", "mouth_2"]) this.layers[k].style.visibility = k === m ? "visible" : "hidden";
        this.layers.eyes_open.style.visibility = blinking ? "hidden" : "visible";
        this.layers.eyes_closed.style.visibility = blinking ? "visible" : "hidden";
      }
      requestAnimationFrame(() => this._loop());
    }
  }

  window.Character = Character;
})();
