/*
 * Soundscape card
 * What the microphones around the house hear, and where it is coming from.
 * Needs the Soundscape integration, which also loads this file.
 *
 *   type: custom:soundscape-card
 *   title: Soundscape
 *   show_radar: true
 *   show_spectrogram: true
 *   show_log: true
 *   mic: auto                 # or a camera name, for the spectrogram
 *   spectrogram_height: 150
 *   spectrogram_seconds: 60
 *   log_rows: 8
 *   range_km: 10              # outer ring of the radar
 */
const VERSION = '0.1.0';

const GROUP = {
  bird: 'life', coyote: 'life', dog: 'life', cat: 'life', voice: 'life',
  vehicle: 'road', horn: 'road', machinery: 'road', weather: 'road',
  siren: 'alert', car_alarm: 'alert', glass: 'alert', bang: 'alert', alarm: 'alert',
  jet: 'air', propeller: 'air', helicopter: 'air', tiltrotor: 'air', aircraft: 'air',
};
const AIR_ICON = { jet: 'mdi:airplane', propeller: 'mdi:airplane', helicopter: 'mdi:helicopter', tiltrotor: 'mdi:quadcopter', aircraft: 'mdi:airplane' };

/* Inferno-like ramp, as in BirdNET-Go's live spectrogram. */
const LUT = (() => {
  const stops = [[0, 0, 4], [27, 12, 65], [74, 12, 107], [120, 28, 109], [165, 44, 96], [207, 68, 70], [237, 105, 37], [251, 155, 6], [247, 209, 61], [252, 255, 164]];
  const lut = new Uint8ClampedArray(256 * 4);
  for (let i = 0; i < 256; i++) {
    const x = (i / 255) * (stops.length - 1);
    const a = stops[Math.floor(x)], b = stops[Math.min(stops.length - 1, Math.floor(x) + 1)], f = x - Math.floor(x);
    for (let c = 0; c < 3; c++) lut[i * 4 + c] = a[c] + (b[c] - a[c]) * f;
    lut[i * 4 + 3] = 255;
  }
  return lut;
})();

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const polar = (bearing, r) => { const a = (bearing - 90) * Math.PI / 180; return [r * Math.cos(a), r * Math.sin(a)]; };

class SoundscapeCard extends HTMLElement {
  static getStubConfig() { return { title: 'Soundscape' }; }

  static getConfigForm() {
    const labels = {
      title: 'Title', show_radar: 'Show the radar', show_spectrogram: 'Show the live spectrogram',
      show_log: 'Show recent sounds', mic: 'Spectrogram microphone (auto, or a camera name)',
      spectrogram_height: 'Spectrogram height', spectrogram_seconds: 'Spectrogram span',
      log_rows: 'Recent sounds to list', range_km: 'Radar range for aircraft',
    };
    return {
      schema: [
        { name: 'title', selector: { text: {} } },
        { type: 'grid', name: '', schema: [
          { name: 'show_radar', selector: { boolean: {} } },
          { name: 'show_spectrogram', selector: { boolean: {} } },
          { name: 'show_log', selector: { boolean: {} } },
        ] },
        { name: 'mic', selector: { text: {} } },
        { type: 'grid', name: '', schema: [
          { name: 'spectrogram_height', selector: { number: { min: 80, max: 400, step: 10, unit_of_measurement: 'px', mode: 'box' } } },
          { name: 'spectrogram_seconds', selector: { number: { min: 15, max: 90, step: 5, unit_of_measurement: 's', mode: 'box' } } },
          { name: 'log_rows', selector: { number: { min: 0, max: 40, step: 1, mode: 'box' } } },
          { name: 'range_km', selector: { number: { min: 2, max: 50, step: 1, unit_of_measurement: 'km', mode: 'box' } } },
        ] },
      ],
      computeLabel: (s) => labels[s.name] || s.name,
    };
  }

  setConfig(config) {
    this._c = {
      title: 'Soundscape', show_radar: true, show_spectrogram: true, show_log: true, mic: 'auto',
      spectrogram_height: 150, spectrogram_seconds: 60, log_rows: 8, range_km: 10, ...config,
    };
    this._mic = this._c.mic && this._c.mic !== 'auto' ? this._c.mic : null;
    this._built = false;
    if (this._state) this._render();
  }

  getCardSize() { return 3 + (this._c.show_radar ? 5 : 0) + (this._c.show_spectrogram ? 4 : 0) + (this._c.show_log ? 4 : 0); }

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected) this._subscribe();
  }

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this._subscribe();
  }

  disconnectedCallback() {
    this._unsub?.then((u) => u && u()).catch(() => {});
    this._unsub = null;
  }

  _subscribe() {
    if (this._unsub || !this._hass?.connection) return;
    this._unsub = this._hass.connection
      .subscribeMessage((m) => this._message(m), { type: 'soundscape/subscribe' })
      .catch((err) => { this._error = err?.message || String(err); this._unsub = null; this._render(); return null; });
  }

  /* ------------------------------------------------------------ messages */
  _message(m) {
    if (m.type === 'init') {
      this._meta = m.meta;
      this._specs = {};
      for (const mic of m.mics) this._spec(mic.id);
      for (const [mic, data] of Object.entries(m.backlog || {})) this._push(mic, b64(data), m.now);
      this._state = m;
      this._error = null;
      this._render();
    } else if (m.type === 'state') {
      this._state = m;
      this._render();
    } else if (m.type === 'spec' && this._meta) {
      this._push(m.mic, b64(m.data), m.t);
      if (m.mic === this._shown) this._paint();
    }
  }

  _spec(mic) {
    if (!this._specs[mic]) {
      const w = Math.ceil(this._meta.backlog_s * this._meta.cols_per_s);
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = this._meta.bands;
      const ctx = canvas.getContext('2d', { willReadFrequently: false });
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, canvas.height);
      this._specs[mic] = { canvas, ctx, t: 0 };
    }
    return this._specs[mic];
  }

  _push(mic, bytes, t) {
    const s = this._spec(mic), bands = this._meta.bands;
    let n = Math.floor(bytes.length / bands);
    if (!n) return;
    const w = s.canvas.width;
    if (n > w) { bytes = bytes.subarray((n - w) * bands); n = w; }
    const img = s.ctx.createImageData(n, bands);
    for (let x = 0; x < n; x++) {
      for (let b = 0; b < bands; b++) {
        const v = bytes[x * bands + b] * 4, o = ((bands - 1 - b) * n + x) * 4;
        img.data[o] = LUT[v]; img.data[o + 1] = LUT[v + 1]; img.data[o + 2] = LUT[v + 2]; img.data[o + 3] = 255;
      }
    }
    s.ctx.globalCompositeOperation = 'copy';
    s.ctx.drawImage(s.canvas, -n, 0);
    s.ctx.globalCompositeOperation = 'source-over';
    s.ctx.putImageData(img, w - n, 0);
    s.t = t;
  }

  /* -------------------------------------------------------------- render */
  _build() {
    const c = this._c;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head"><ha-icon icon="mdi:waveform"></ha-icon><span class="title"></span><span class="status"></span></div>
        <div class="now"></div>
        <div class="why" hidden></div>
        ${c.show_radar ? '<div class="radar"></div>' : ''}
        ${c.show_spectrogram ? `<div class="spec">
          <div class="pills"></div>
          <div class="frame" style="height:${Number(c.spectrogram_height) || 150}px">
            <canvas></canvas><div class="marks"></div><div class="hz"></div>
            <div class="span"></div>
          </div></div>` : ''}
        ${c.show_log && c.log_rows > 0 ? '<div class="log"></div>' : ''}
      </ha-card>`;
    const root = this.shadowRoot;
    root.querySelector('.title').textContent = c.title || '';
    if (!this._wired) {
      this._wired = true;
      root.addEventListener('click', (e) => {
        const pill = e.target.closest('[data-mic]');
        if (pill) { this._mic = pill.dataset.mic || null; this._render(); return; }
        const ev = e.target.closest('[data-ev]');
        if (ev) { this._open = this._open === ev.dataset.ev ? null : ev.dataset.ev; this._render(); }
      });
    }
    this._canvas = root.querySelector('canvas');
    if (this._canvas && !this._ro) {
      this._ro = new ResizeObserver(() => this._paint());
    }
    if (this._canvas) this._ro.observe(this._canvas);
    this._built = true;
  }

  _render() {
    if (!this.shadowRoot) return;
    if (this._error && !this._state) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="empty">Soundscape is not answering: ${esc(this._error)}.<br>Is the Soundscape integration set up?</div></ha-card>`;
      this._built = false;
      return;
    }
    if (!this._state) return;
    if (!this._built) this._build();
    const st = this._state, root = this.shadowRoot;
    const down = st.mics.filter((m) => !m.ok);
    const status = root.querySelector('.status');
    status.textContent = down.length ? `${down.length} of ${st.mics.length} microphones silent` : `${st.mics.length} microphones`;
    status.title = down.map((m) => `${m.name}: ${m.error || 'no audio'}`).join('\n');
    status.classList.toggle('bad', down.length > 0);

    /* now hearing */
    const now = root.querySelector('.now');
    now.innerHTML = st.active.length ? st.active.map((e) => this._chip(e)).join('') : '<div class="quiet">Quiet</div>';
    const all = [...st.active, ...st.recent];
    const open = all.find((e) => String(e.id) === this._open);
    const why = root.querySelector('.why');
    why.hidden = !open;
    if (open) {
      const disp = (open.extra?.dispatch || []).map((d) => `<li>Dispatch: ${esc(d.type)}, ${esc(d.address)}${d.cross ? ' at ' + esc(d.cross) : ''} (${esc(d.units)}), ${clock(Date.parse(d.time) / 1000)}, about ${d.km} km</li>`);
      const lines = open.evidence.filter((t) => !t.startsWith('Dispatch')).map((t) => `<li>${esc(t)}</li>`);
      why.innerHTML = `<b>${esc(open.label)}</b> · ${Math.round(open.conf * 100)}% · ${clock(open.start)}<ul>${lines.join('')}${disp.join('')}</ul>${this._levels(open)}`;
    }

    if (this._c.show_radar) root.querySelector('.radar').innerHTML = this._radar(st);
    if (this._c.show_spectrogram) this._specUi(st);
    const log = root.querySelector('.log');
    if (log) {
      const rows = st.recent.slice(0, this._c.log_rows);
      log.innerHTML = rows.length ? rows.map((e) => `
        <div class="row g-${GROUP[e.cls] || 'road'}${String(e.id) === this._open ? ' sel' : ''}" data-ev="${e.id}">
          <span class="t">${clock(e.start)}</span><ha-icon icon="${esc(e.icon)}"></ha-icon>
          <span class="l">${esc(e.label)}</span><span class="w">${esc(this._where(e))}</span>
          <span class="d">${Math.max(1, Math.round((e.end || st.now) - e.start))} s</span>
        </div>`).join('') : '<div class="none">Nothing logged yet</div>';
    }
  }

  _where(e) {
    if (e.method === 'adsb') return e.detail;
    if (e.far) return 'Overhead or distant';
    const mic = this._state.mics.find((m) => m.id === e.mic);
    return [mic?.name, e.compass].filter(Boolean).join(' · ');
  }

  _chip(e) {
    return `<div class="chip g-${GROUP[e.cls] || 'road'}${String(e.id) === this._open ? ' sel' : ''}" data-ev="${e.id}">
      <ha-icon icon="${esc(e.icon)}"></ha-icon>
      <div><div class="l">${esc(e.label)}</div><div class="w">${esc(this._where(e)) || '&nbsp;'}</div></div>
      <span class="c">${Math.round(e.conf * 100)}%</span></div>`;
  }

  _levels(e) {
    const entries = Object.entries(e.levels || {});
    if (!entries.length || e.method === 'adsb') return '';
    const max = Math.max(6, ...entries.map(([, v]) => v));
    return `<div class="lv">${entries.sort((a, b) => b[1] - a[1]).map(([id, v]) => {
      const mic = this._state.mics.find((m) => m.id === id);
      return `<span>${esc(mic?.name || id)}</span><i><b style="width:${Math.max(0, v) / max * 100}%"></b></i><span>${v > 0 ? '+' : ''}${Math.round(v)} dB</span>`;
    }).join('')}</div>`;
  }

  /* --------------------------------------------------------------- radar */
  _radar(st) {
    const R_MICS = 26, R_NEAR = 44, R_IN = 58, R_OUT = 98, range = Math.max(2, this._c.range_km);
    const far = Math.max(1, ...st.mics.map((m) => m.distance));
    const km = (d) => R_IN + (R_OUT - R_IN) * Math.min(1, Math.log(Math.max(0.3, d) / 0.3) / Math.log(range / 0.3));
    let s = `<svg viewBox="-112 -106 224 212" role="img" aria-label="Where sounds are coming from">`;
    s += `<circle class="ground" r="${R_IN - 4}"/>`;
    for (const d of [1, range / 2, range].filter((d, i, a) => d > 0.3 && a.indexOf(d) === i)) {
      s += `<circle class="ring" r="${km(d)}"/><text class="rl" x="3" y="${-km(d) + 7}">${+d.toFixed(1)} km</text>`;
    }
    for (const [b, t] of [[0, 'N'], [90, 'E'], [180, 'S'], [270, 'W']]) {
      const [x, y] = polar(b, 104);
      s += `<text class="nesw" x="${x}" y="${y + 3}">${t}</text>`;
    }
    s += `<path class="house" d="M-7 4 V-3 L0 -9 L7 -3 V4 Z"/>`;

    /* sounds on the ground: a wedge toward where they are loudest */
    const air = new Set();
    for (const e of st.active) {
      const g = GROUP[e.cls] || 'road';
      if (e.method === 'adsb') { air.add(e.extra?.aircraft?.hex); continue; }
      if (e.far || e.bearing == null) {
        s += `<circle class="far g-${g}" r="${R_NEAR + 5}"/>`;
        continue;
      }
      const [x1, y1] = polar(e.bearing - 24, R_IN - 4), [x2, y2] = polar(e.bearing + 24, R_IN - 4);
      const [ix, iy] = polar(e.bearing, R_NEAR);
      s += `<path class="wedge g-${g}" d="M0 0 L${x1} ${y1} A${R_IN - 4} ${R_IN - 4} 0 0 1 ${x2} ${y2} Z"/>`;
      s += `<g class="ev g-${g}" transform="translate(${ix} ${iy})"><circle r="8"/><foreignObject x="-6" y="-6" width="12" height="12"><ha-icon icon="${esc(e.icon)}"></ha-icon></foreignObject></g>`;
    }

    /* microphones, each with a halo for how far above its own background it is */
    for (const m of st.mics) {
      const [x, y] = polar(m.bearing, 6 + (R_MICS - 6) * (m.distance / far));
      const halo = m.ok ? Math.min(8, Math.max(0, m.excess) * 0.4) : 0;
      const [lx, ly] = polar(m.bearing, 6 + (R_MICS - 6) * (m.distance / far) + 6);
      s += `<circle class="halo" cx="${x}" cy="${y}" r="${2 + halo}"/><circle class="mic${m.ok ? '' : ' off'}" cx="${x}" cy="${y}" r="2"><title>${esc(m.name)}${m.ok ? ` ${m.level} dBFS` : ': ' + esc(m.error || 'no audio')}</title></circle>`;
      s += `<text class="ml" x="${lx}" y="${ly + 2}" text-anchor="${Math.abs(lx) < 4 ? 'middle' : lx > 0 ? 'start' : 'end'}">${esc(m.name)}</text>`;
    }

    /* aircraft, where their sound is arriving from */
    for (const a of st.aircraft) {
      if (a.km > range * 1.15) continue;
      const hot = air.has(a.hex);
      const [x, y] = polar(hot ? a.heard_bearing : a.bearing, km(hot ? a.heard_km : a.km));
      const name = a.flight || a.reg || a.type || '';
      s += `<g class="ac${hot ? ' hot' : ''}${a.audible >= 0.25 ? ' near' : ''}" transform="translate(${x} ${y})">
        <title>${esc([a.desc || a.type, name, a.alt_ft + ' ft', a.km + ' km'].filter(Boolean).join(' · '))}</title>
        ${hot ? '<circle class="pulse" r="9"/>' : ''}
        <g transform="rotate(${a.track})"><path d="${a.cls === 'helicopter' || a.cls === 'tiltrotor' ? 'M-4.5 -4.5 L4.5 4.5 M-4.5 4.5 L4.5 -4.5 M-1.6 0 A1.6 1.6 0 1 0 1.6 0 A1.6 1.6 0 1 0 -1.6 0' : 'M0 -5 L3.4 4 L0 2 L-3.4 4 Z'}"/></g>
        ${hot || a.audible >= 0.25 ? `<text x="6" y="2.5">${esc(a.type === 'V22' ? 'Osprey' : a.type || name)}${hot && name ? ' ' + esc(name) : ''}</text>` : ''}
      </g>`;
    }
    return s + '</svg>';
  }

  /* --------------------------------------------------------- spectrogram */
  _specUi(st) {
    const root = this.shadowRoot;
    let shown = this._mic;
    if (!shown || !st.mics.some((m) => m.id === shown)) {
      const ok = st.mics.filter((m) => m.ok);
      const lead = st.active.find((e) => e.mic)?.mic;
      const best = ok.slice().sort((a, b) => b.excess - a.excess)[0];
      const cur = ok.find((m) => m.id === this._auto);
      if (lead && ok.some((m) => m.id === lead)) this._auto = lead;
      else if (!cur || (best && best.excess > cur.excess + 4)) this._auto = best?.id || st.mics[0]?.id;
      shown = this._auto;
    }
    this._shown = shown;
    root.querySelector('.pills').innerHTML =
      `<span class="pill${this._mic ? '' : ' on'}" data-mic="">Auto</span>` +
      st.mics.map((m) => `<span class="pill${m.id === shown ? (this._mic ? ' on' : ' cur') : ''}${m.ok ? '' : ' off'}" data-mic="${esc(m.id)}">${esc(m.name)}</span>`).join('');
    const secs = Math.min(this._meta.backlog_s, Math.max(10, this._c.spectrogram_seconds));
    const edges = this._meta.edges, lo = Math.log(edges[0]), hi = Math.log(edges[edges.length - 1]);
    root.querySelector('.hz').innerHTML = [100, 300, 1000, 3000, 10000].filter((f) => f > edges[0] * 1.2 && f < edges[edges.length - 1] * 0.8)
      .map((f) => `<span style="bottom:${(Math.log(f) - lo) / (hi - lo) * 100}%">${f >= 1000 ? f / 1000 + ' kHz' : f + ' Hz'}</span>`).join('');
    root.querySelector('.span').textContent = `last ${secs} s`;
    const t1 = this._specs?.[shown]?.t || st.now;
    const marks = [...st.active, ...st.recent].filter((e) => e.start > t1 - secs && (e.far || !e.mic || e.mic === shown));
    root.querySelector('.marks').innerHTML = marks.map((e) => {
      const x = (1 - (t1 - e.start) / secs) * 100;
      return `<span class="g-${GROUP[e.cls] || 'road'}" style="left:${Math.max(0, x)}%">${esc(e.label)}</span>`;
    }).join('');
    this._paint();
  }

  _paint() {
    const cv = this._canvas, s = this._specs?.[this._shown];
    if (!cv || !s || !cv.clientWidth) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.round(cv.clientWidth * dpr), h = Math.round(cv.clientHeight * dpr);
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    const secs = Math.min(this._meta.backlog_s, Math.max(10, this._c.spectrogram_seconds));
    const cols = Math.min(s.canvas.width, Math.round(secs * this._meta.cols_per_s));
    const ctx = cv.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(s.canvas, s.canvas.width - cols, 0, cols, s.canvas.height, 0, 0, w, h);
  }
}

const STYLE = `
  :host { --life: #43a047; --road: #78909c; --alert: #e53935; --air: #1e88e5; }
  ha-card { padding: 12px 14px 14px; overflow: hidden; }
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .head ha-icon { color: var(--secondary-text-color); --mdc-icon-size: 20px; }
  .title { font-size: 16px; font-weight: 500; flex: 1; color: var(--primary-text-color); }
  .status { font-size: 12px; color: var(--secondary-text-color); }
  .status.bad { color: var(--warning-color, #f9a825); }
  .empty, .none, .quiet { color: var(--secondary-text-color); font-size: 14px; padding: 6px 0; }
  .quiet { padding: 9px 0; }
  .g-life { --g: var(--life); } .g-road { --g: var(--road); } .g-alert { --g: var(--alert); } .g-air { --g: var(--air); }
  .now { display: flex; flex-wrap: wrap; gap: 8px; min-height: 40px; }
  .chip { display: flex; align-items: center; gap: 8px; padding: 5px 10px 5px 8px; border-radius: 12px; cursor: pointer;
    background: color-mix(in srgb, var(--g) 14%, transparent); border: 1px solid color-mix(in srgb, var(--g) 45%, transparent);
    max-width: 100%; box-sizing: border-box; }
  .chip.sel { border-color: var(--g); }
  .chip ha-icon { color: var(--g); --mdc-icon-size: 22px; flex: none; }
  .chip .l { font-size: 14px; font-weight: 500; color: var(--primary-text-color); line-height: 1.25; }
  .chip .w { font-size: 12px; color: var(--secondary-text-color); line-height: 1.25; }
  .chip .c { font-size: 11px; color: var(--secondary-text-color); margin-left: 2px; }
  .why { margin-top: 8px; padding: 8px 10px; border-radius: 10px; font-size: 12.5px; color: var(--primary-text-color);
    background: var(--secondary-background-color, rgba(127,127,127,.12)); }
  .why ul { margin: 4px 0 0; padding-left: 18px; color: var(--secondary-text-color); }
  .lv { display: grid; grid-template-columns: auto 1fr auto; gap: 3px 8px; align-items: center; margin-top: 6px; color: var(--secondary-text-color); }
  .lv i { height: 5px; border-radius: 3px; background: color-mix(in srgb, var(--primary-text-color) 12%, transparent); }
  .lv b { display: block; height: 100%; border-radius: 3px; background: var(--primary-color); }
  .radar { margin: 6px auto 0; max-width: 430px; }
  svg { display: block; width: 100%; overflow: visible; }
  .ground { fill: color-mix(in srgb, var(--primary-text-color) 5%, transparent); stroke: var(--divider-color); stroke-width: .6; }
  .ring { fill: none; stroke: var(--divider-color); stroke-width: .5; stroke-dasharray: 1.5 2.5; }
  text { font: 5.4px var(--mdc-typography-font-family, Roboto, sans-serif); fill: var(--secondary-text-color); }
  .rl { font-size: 4.6px; opacity: .8; }
  .nesw { text-anchor: middle; font-weight: 500; }
  .house { fill: var(--secondary-text-color); opacity: .55; }
  .mic { fill: var(--primary-text-color); } .mic.off { fill: var(--warning-color, #f9a825); }
  .halo { fill: var(--primary-color); opacity: .28; transition: r .6s; }
  .ml { font-size: 4.6px; }
  .wedge { fill: var(--g); opacity: .22; }
  .far { fill: none; stroke: var(--g); stroke-width: 5; opacity: .3; animation: breathe 2s ease-in-out infinite; }
  .ev circle { fill: var(--card-background-color, #fff); stroke: var(--g); stroke-width: 1.2; }
  .ev ha-icon { --mdc-icon-size: 10px; color: var(--g); display: block; width: 12px; height: 12px; line-height: 12px; text-align: center; }
  .ac path { fill: var(--secondary-text-color); stroke: var(--secondary-text-color); stroke-width: .8; opacity: .45; }
  .ac.near path { opacity: .9; }
  .ac.hot path { fill: var(--air); stroke: var(--air); opacity: 1; }
  .ac text { font-size: 4.8px; } .ac.hot text { fill: var(--air); font-weight: 500; }
  .pulse { fill: none; stroke: var(--air); stroke-width: 1; animation: breathe 1.6s ease-in-out infinite; }
  @keyframes breathe { 0%, 100% { opacity: .15; } 50% { opacity: .6; } }
  .spec { margin-top: 10px; }
  .pills { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
  .pill { font-size: 12px; padding: 2px 9px; border-radius: 10px; cursor: pointer; color: var(--secondary-text-color);
    border: 1px solid var(--divider-color); }
  .pill.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .pill.cur { border-color: var(--primary-color); color: var(--primary-text-color); }
  .pill.off { text-decoration: line-through; }
  .frame { position: relative; border-radius: 8px; overflow: hidden; background: #000; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
  .hz span { position: absolute; left: 4px; transform: translateY(50%); font-size: 9.5px; color: rgba(255,255,255,.7); text-shadow: 0 0 3px #000; }
  .span { position: absolute; right: 6px; bottom: 3px; font-size: 9.5px; color: rgba(255,255,255,.6); text-shadow: 0 0 3px #000; }
  .marks span { position: absolute; top: 0; bottom: 0; border-left: 1px solid color-mix(in srgb, var(--g) 80%, #fff);
    padding: 2px 4px; font-size: 10.5px; font-weight: 500; color: #fff; text-shadow: 0 0 3px #000, 0 0 2px #000; white-space: nowrap; }
  .log { margin-top: 10px; border-top: 1px solid var(--divider-color); padding-top: 6px; }
  .row { display: grid; grid-template-columns: 58px 20px auto 1fr auto; gap: 8px; align-items: center; padding: 3px 0; cursor: pointer; font-size: 13px; }
  .row.sel { background: var(--secondary-background-color, rgba(127,127,127,.12)); border-radius: 6px; }
  .row ha-icon { --mdc-icon-size: 18px; color: var(--g); }
  .row .t, .row .d, .row .w { color: var(--secondary-text-color); font-size: 12px; }
  .row .w { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row .l { color: var(--primary-text-color); white-space: nowrap; }
`;

if (!customElements.get('soundscape-card')) {
  customElements.define('soundscape-card', SoundscapeCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'soundscape-card', name: 'Soundscape',
    description: 'What the microphones around the house hear, and where it is coming from.',
    preview: false, documentationURL: 'https://github.com/FortranFour/soundscape',
  });
  console.info(`%c SOUNDSCAPE-CARD %c ${VERSION} `, 'background:#4a0c6b;color:#fff', 'background:#fb9b06;color:#000');
}
