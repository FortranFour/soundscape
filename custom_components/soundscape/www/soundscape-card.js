/*
 * Soundscape card
 * What the microphones around the house hear, and where it is coming from.
 * Needs the Soundscape integration, which also loads this file.
 *
 *   type: custom:soundscape-card
 *   title: Soundscape
 *   show_radar: true
 *   radar: schematic          # or: map
 *   map_style: streets        # or: satellite
 *   map_radius_m: 60          # how far the map reaches from the house
 *   range_km: 10              # outer ring of the schematic radar
 *   radar_recent_seconds: 120 # keep ended sounds on the radar, faded, this long
 *   units: auto               # or: km, mi
 *   show_spectrogram: true
 *   mic: auto                 # or a camera name
 *   spectrogram_height: 150
 *   spectrogram_seconds: 60
 *   show_listen: true         # live audio button
 *   volume: 80
 *   show_log: true
 *   log_rows: 8               # rows visible before the list scrolls
 *   log_max: 100              # rows kept in the list
 *   log_hide: []              # kinds to leave out, e.g. [vehicle, voice]
 */
const VERSION = '0.2.0';

const GROUP = {
  bird: 'life', coyote: 'life', dog: 'life', cat: 'life', voice: 'life',
  vehicle: 'road', horn: 'road', machinery: 'road', weather: 'road',
  siren: 'alert', car_alarm: 'alert', glass: 'alert', bang: 'alert', alarm: 'alert',
  jet: 'air', propeller: 'air', helicopter: 'air', tiltrotor: 'air', aircraft: 'air',
};
const GROUP_NAME = { life: 'Wildlife and people', road: 'Road and yard', alert: 'Alerts', air: 'Aircraft' };
const KINDS = {
  bird: 'Birds', coyote: 'Coyotes', dog: 'Dogs', cat: 'Cats', voice: 'Voices', vehicle: 'Vehicles', horn: 'Horns',
  machinery: 'Machinery', weather: 'Weather', siren: 'Sirens', car_alarm: 'Car alarms', glass: 'Breaking glass',
  bang: 'Bangs', alarm: 'Alarms', jet: 'Jets', propeller: 'Propeller aircraft', helicopter: 'Helicopters',
  tiltrotor: 'Ospreys', aircraft: 'Other aircraft',
};

/* Aircraft seen from above, nose up, in a box about 14 units wide. [filled outline, stroked detail] */
const PLANE = {
  jet: ['M0 -7 L1.3 -2.4 L7 3 L7 4.3 L1.3 2.4 L1 5.6 L3 6.9 L3 7.6 L-3 7.6 L-3 6.9 L-1 5.6 L-1.3 2.4 L-7 4.3 L-7 3 L-1.3 -2.4 Z', ''],
  propeller: ['M0 -6 L1.1 -2.8 L7.2 -2.3 L7.2 -0.5 L1.1 0 L0.8 5 L2.8 5.6 L2.8 6.6 L-2.8 6.6 L-2.8 5.6 L-0.8 5 L-1.1 0 L-7.2 -0.5 L-7.2 -2.3 L-1.1 -2.8 Z', 'M-2.6 -6.3 H2.6'],
  helicopter: ['M0 -3.6 C2.4 -3.6 2.4 2.2 0.7 2.8 L0.5 6.4 L2 6.4 L2 7.4 L-2 7.4 L-2 6.4 L-0.5 6.4 L-0.7 2.8 C-2.4 2.2 -2.4 -3.6 0 -3.6 Z', 'M-6.4 -0.6 A6.4 6.4 0 1 0 6.4 -0.6 A6.4 6.4 0 1 0 -6.4 -0.6 M-4.5 -5.1 L4.5 3.9 M-4.5 3.9 L4.5 -5.1'],
  tiltrotor: ['M0 -6 L1.1 -3.6 L1.1 -2 L6 -2 L6 -0.2 L1.1 -0.2 L1.1 4.4 L2.8 5.8 L2.8 6.6 L-2.8 6.6 L-2.8 5.8 L-1.1 4.4 L-1.1 -0.2 L-6 -0.2 L-6 -2 L-1.1 -2 L-1.1 -3.6 Z', 'M-9 -1.1 A3 3 0 1 0 -3 -1.1 A3 3 0 1 0 -9 -1.1 M3 -1.1 A3 3 0 1 0 9 -1.1 A3 3 0 1 0 3 -1.1'],
  aircraft: ['M0 -6 L4 5.5 L0 3 L-4 5.5 Z', ''],
};

const TILES = {
  streets: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png', '© OpenStreetMap contributors', 19],
  satellite: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Imagery © Esri and its data providers', 19],
};

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
const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
const compass = (b) => COMPASS[Math.round((((b % 360) + 360) % 360) / 45) % 8];
const nice = (x) => { const p = 10 ** Math.floor(Math.log10(x)); const f = x / p; return (f >= 5 ? 5 : f >= 2 ? 2 : 1) * p; };

class SoundscapeCard extends HTMLElement {
  static getStubConfig() { return { title: 'Soundscape' }; }

  static getConfigForm() {
    const labels = {
      title: 'Title', show_radar: 'Radar', show_spectrogram: 'Live spectrogram', show_log: 'Recent sounds',
      show_listen: 'Listen button', radar: 'Radar background', map_style: 'Map', map_radius_m: 'Map reaches',
      range_km: 'Schematic range for aircraft', radar_recent_seconds: 'Keep ended sounds on the radar',
      units: 'Distances', mic: 'Spectrogram microphone (auto, or a camera name)',
      spectrogram_height: 'Spectrogram height', spectrogram_seconds: 'Spectrogram span', volume: 'Starting volume',
      log_rows: 'Rows before the list scrolls', log_max: 'Rows kept', log_hide: 'Leave out of the list',
    };
    const num = (min, max, step, unit) => ({ number: { min, max, step, mode: 'box', ...(unit ? { unit_of_measurement: unit } : {}) } });
    const pick = (options) => ({ select: { mode: 'dropdown', options } });
    return {
      schema: [
        { name: 'title', selector: { text: {} } },
        { type: 'grid', name: '', schema: [
          { name: 'show_radar', selector: { boolean: {} } }, { name: 'show_spectrogram', selector: { boolean: {} } },
          { name: 'show_log', selector: { boolean: {} } }, { name: 'show_listen', selector: { boolean: {} } },
        ] },
        { type: 'expandable', name: '', title: 'Radar and map', schema: [
          { type: 'grid', name: '', schema: [
            { name: 'radar', selector: pick([{ value: 'schematic', label: 'Schematic (logarithmic distance)' }, { value: 'map', label: 'Map (true scale)' }]) },
            { name: 'map_style', selector: pick([{ value: 'streets', label: 'Streets' }, { value: 'satellite', label: 'Satellite' }]) },
            { name: 'map_radius_m', selector: num(20, 20000, 10, 'm') },
            { name: 'range_km', selector: num(2, 50, 1, 'km') },
            { name: 'radar_recent_seconds', selector: num(0, 900, 10, 's') },
            { name: 'units', selector: pick([{ value: 'auto', label: 'Automatic' }, { value: 'km', label: 'Kilometres' }, { value: 'mi', label: 'Miles' }]) },
          ] },
        ] },
        { type: 'expandable', name: '', title: 'Spectrogram and listening', schema: [
          { name: 'mic', selector: { text: {} } },
          { type: 'grid', name: '', schema: [
            { name: 'spectrogram_height', selector: num(80, 400, 10, 'px') },
            { name: 'spectrogram_seconds', selector: num(15, 90, 5, 's') },
            { name: 'volume', selector: num(0, 100, 5, '%') },
          ] },
        ] },
        { type: 'expandable', name: '', title: 'Recent sounds', schema: [
          { type: 'grid', name: '', schema: [
            { name: 'log_rows', selector: num(1, 40, 1) }, { name: 'log_max', selector: num(5, 150, 5) },
          ] },
          { name: 'log_hide', selector: { select: { multiple: true, mode: 'dropdown', options: Object.entries(KINDS).map(([value, label]) => ({ value, label })) } } },
        ] },
      ],
      computeLabel: (s) => labels[s.name] || s.name,
    };
  }

  setConfig(config) {
    this._c = {
      title: 'Soundscape', show_radar: true, radar: 'schematic', map_style: 'streets', map_radius_m: 60,
      range_km: 10, radar_recent_seconds: 120, units: 'auto', show_spectrogram: true, mic: 'auto',
      spectrogram_height: 150, spectrogram_seconds: 60, show_listen: true, volume: 80,
      show_log: true, log_rows: 8, log_max: 100, log_hide: [], ...config,
    };
    this._mic = this._c.mic && this._c.mic !== 'auto' ? this._c.mic : null;
    this._volume = Math.min(1, Math.max(0, (Number(this._c.volume) || 0) / 100));
    this._built = false;
    this._sig = {};
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
    this._listenStop();
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
      this._built = false;
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
      const ctx = canvas.getContext('2d');
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

  /* --------------------------------------------------------------- units */
  get _mi() { return (this._c.units === 'auto' ? this._meta?.units : this._c.units) === 'mi'; }

  _dist(km) {
    if (this._mi) { const mi = km / 1.609344; return mi >= 0.1 ? `${mi.toFixed(1)} mi` : `${Math.round(km * 328.084) * 10} ft`; }
    return km >= 0.1 ? `${km.toFixed(1)} km` : `${Math.round(km * 100) * 10} m`;
  }

  /* -------------------------------------------------------------- render */
  _build() {
    const c = this._c, map = c.radar === 'map';
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head"><ha-icon icon="mdi:waveform"></ha-icon><span class="title"></span><span class="status"></span></div>
        <div class="now"></div>
        <div class="why" hidden></div>
        ${c.show_radar ? `<div class="radar${map ? ' map' : ''}">${map ? '<div class="tiles"></div>' : ''}<div class="plot"></div>${map ? '<div class="credit"></div>' : ''}</div>` : ''}
        ${c.show_spectrogram ? `<div class="spec">
          <div class="bar"><div class="pills"></div>
            ${c.show_listen ? `<div class="listen">
              <button class="hear" title="Listen live"><ha-icon icon="mdi:headphones"></ha-icon></button>
              <button class="mute" title="Mute" hidden><ha-icon icon="mdi:volume-high"></ha-icon></button>
              <input class="vol" type="range" min="0" max="100" step="1" value="${Math.round(this._volume * 100)}" title="Volume" hidden>
            </div>` : ''}
          </div>
          <div class="frame" style="height:${Number(c.spectrogram_height) || 150}px">
            <canvas></canvas><div class="marks"></div><div class="hz"></div>
            <div class="span"></div>
          </div></div>` : ''}
        ${c.show_log ? `<div class="logwrap"><div class="filters"></div>
          <div class="log" style="max-height:${Math.max(1, Number(c.log_rows) || 8) * 28}px"></div></div>` : ''}
      </ha-card>`;
    const root = this.shadowRoot;
    root.querySelector('.title').textContent = c.title || '';
    if (!this._wired) {
      this._wired = true;
      root.addEventListener('click', (e) => {
        const hit = (sel) => e.target.closest(sel);
        if (hit('.hear')) { this._listening ? this._listenStop() : this._listenStart(); return; }
        if (hit('.mute')) { this._muted = !this._muted; this._listenUi(); return; }
        const pill = hit('[data-mic]');
        if (pill) { this._mic = pill.dataset.mic || null; this._render(); return; }
        const filter = hit('[data-filter]');
        if (filter) { this._filter = filter.dataset.filter || null; this._render(); return; }
        const ev = hit('[data-ev]');
        if (ev) { this._open = this._open === ev.dataset.ev ? null : ev.dataset.ev; this._render(); }
      });
      root.addEventListener('input', (e) => {
        if (e.target.classList?.contains('vol')) { this._volume = e.target.value / 100; this._muted = false; this._listenUi(); }
      });
    }
    this._canvas = root.querySelector('canvas');
    if (this._canvas) {
      this._ro = this._ro || new ResizeObserver(() => this._paint());
      this._ro.observe(this._canvas);
    }
    if (map) this._tiles();
    this._sig = {};
    this._built = true;
    this._listenUi();
  }

  /* innerHTML only when the content changed: keeps scroll position, hover and sliders steady */
  _set(sel, htmlText) {
    const el = this.shadowRoot.querySelector(sel);
    if (el && this._sig[sel] !== htmlText) { this._sig[sel] = htmlText; el.innerHTML = htmlText; }
    return el;
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

    this._set('.now', st.active.length ? st.active.map((e) => this._chip(e)).join('') : '<div class="quiet">Quiet</div>');
    const open = [...st.active, ...st.recent].find((e) => String(e.id) === this._open);
    const why = root.querySelector('.why');
    why.hidden = !open;
    if (open) {
      const disp = (open.extra?.dispatch || []).map((d) => `<li>${esc(d.agency || 'Dispatch')}: ${esc(d.type)}, ${esc(d.address)}${d.cross ? ' at ' + esc(d.cross) : ''}${d.units ? ` (${esc(d.units)})` : ''}, ${clock(Date.parse(d.time) / 1000)}, ${d.exact ? '' : 'about '}${this._dist(d.km)}</li>`);
      const lines = open.evidence.filter((t) => !t.startsWith('Dispatch')).map((t) => `<li>${esc(t)}</li>`);
      this._set('.why', `<b>${esc(open.label)}</b> · ${Math.round(open.conf * 100)}% · ${clock(open.start)}<ul>${lines.join('')}${disp.join('')}</ul>${this._levels(open)}`);
    }

    if (this._c.show_radar) this._set('.plot', this._c.radar === 'map' ? this._mapPlot(st) : this._radar(st));
    if (this._c.show_spectrogram) this._specUi(st);
    if (this._c.show_log) this._log(st);
  }

  _log(st) {
    const hide = new Set(this._c.log_hide || []);
    const all = st.recent.filter((e) => !hide.has(e.cls));
    const groups = [...new Set(all.map((e) => GROUP[e.cls] || 'road'))];
    if (this._filter && !groups.includes(this._filter)) this._filter = null;
    this._set('.filters', groups.length > 1
      ? `<span class="pill${this._filter ? '' : ' on'}" data-filter="">All</span>` + ['life', 'road', 'alert', 'air'].filter((g) => groups.includes(g))
        .map((g) => `<span class="pill g-${g}${this._filter === g ? ' on' : ''}" data-filter="${g}">${GROUP_NAME[g]}</span>`).join('')
      : '');
    const rows = all.filter((e) => !this._filter || (GROUP[e.cls] || 'road') === this._filter).slice(0, Math.max(1, this._c.log_max));
    this._set('.log', rows.length ? rows.map((e) => `
      <div class="row g-${GROUP[e.cls] || 'road'}${String(e.id) === this._open ? ' sel' : ''}" data-ev="${e.id}">
        <span class="t">${clock(e.start)}</span><ha-icon icon="${esc(e.icon)}"></ha-icon>
        <span class="l">${esc(e.label)}</span><span class="w">${esc(this._where(e))}</span>
        <span class="d">${Math.max(1, Math.round((e.end || st.now) - e.start))} s</span>
      </div>`).join('') : '<div class="none">Nothing logged yet</div>');
  }

  _where(e) {
    const a = e.extra?.aircraft;
    if (e.method === 'adsb' && a) {
      return [[a.desc || a.type || 'Unknown type', a.flight || a.reg].filter(Boolean).join(' '),
        `${this._dist(a.heard_km)} ${compass(a.heard_bearing)}`, `${a.alt_ft.toLocaleString()} ft`].join(' · ');
    }
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

  /* ------------------------------------------------------ radar elements */
  _plane(a, x, y, hot, label) {
    const [body, detail] = PLANE[a.cls] || PLANE.aircraft;
    const name = a.flight || a.reg || '';
    const kind = a.type === 'V22' ? 'Osprey' : a.type || name;
    return `<g class="ac${hot ? ' hot' : ''}${a.audible >= 0.25 ? ' near' : ''}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})">
      <title>${esc([a.desc || a.type, name, a.alt_ft.toLocaleString() + ' ft', this._dist(a.km)].filter(Boolean).join(' · '))}</title>
      ${hot ? '<circle class="pulse" r="12"/>' : ''}
      <g transform="rotate(${a.cls === 'helicopter' ? 0 : a.track}) scale(${hot ? 1 : 0.8})"><path class="body" d="${body}"/>${detail ? `<path class="detail" d="${detail}"/>` : ''}</g>
      ${label ? `<text x="${x > 45 ? -10 : 10}" y="2.5"${x > 45 ? ' text-anchor="end"' : ''}>${esc(kind)}${hot && name && name !== kind ? ' ' + esc(name) : ''}${label === 'far' ? ' ' + this._dist(a.heard_km) : ''}</text>` : ''}
    </g>`;
  }

  _sound(e, x, y, old) {
    const g = GROUP[e.cls] || 'road';
    return `<g class="ev g-${g}${old ? ' old' : ''}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})" data-ev="${e.id}">
      <title>${esc(e.label)}${old ? ' · ' + clock(e.start) : ''}</title>
      <circle r="${old ? 6 : 8}"/><foreignObject x="-6" y="-6" width="12" height="12"><div class="ic"><ha-icon icon="${esc(e.icon)}"></ha-icon></div></foreignObject>
      ${old ? '' : `<text class="el" y="14">${esc(e.label.length > 22 ? e.label.slice(0, 21) + '…' : e.label)}</text>`}
    </g>`;
  }

  /* Ground sounds: live ones as a wedge with an icon, ended ones as a fading icon. */
  _sounds(st, rWedge, rIcon) {
    let s = '';
    const keep = Number(this._c.radar_recent_seconds) || 0, used = [];
    const spot = (bearing, r) => { // nudge icons that would land on top of each other
      let rr = r;
      while (used.some(([b, q]) => Math.abs(((b - bearing + 540) % 360) - 180) < 22 && Math.abs(q - rr) < 14)) rr -= 15;
      used.push([bearing, rr]);
      return polar(bearing, Math.max(14, rr));
    };
    for (const e of st.active) {
      if (e.method === 'adsb') continue;
      const g = GROUP[e.cls] || 'road';
      if (e.far || e.bearing == null) {
        s += `<circle class="far g-${g}" r="${rIcon + 6}"/>`;
        const [x, y] = spot(315, rIcon + 6);
        s += this._sound(e, x, y, false);
        continue;
      }
      const [x1, y1] = polar(e.bearing - 24, rWedge), [x2, y2] = polar(e.bearing + 24, rWedge);
      s += `<path class="wedge g-${g}" d="M0 0 L${x1.toFixed(1)} ${y1.toFixed(1)} A${rWedge} ${rWedge} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z"/>`;
      const [x, y] = spot(e.bearing, rIcon);
      s += this._sound(e, x, y, false);
    }
    if (keep) {
      for (const e of st.recent) {
        if (st.now - (e.end || 0) > keep) break;
        if (e.method === 'adsb' || e.far || e.bearing == null) continue;
        const [x, y] = spot(e.bearing, rIcon);
        s += this._sound(e, x, y, true);
      }
    }
    return s;
  }

  _mics(st, place) {
    let s = '';
    const spread = Math.max(0, ...st.mics.map((m) => Math.hypot(...place(m).slice(0, 2))));
    for (const m of st.mics) {
      const [x, y, lx, ly] = place(m);
      if (spread < 9) continue;   // zoomed out so far that they all sit on the house
      const halo = m.ok ? Math.min(8, Math.max(0, m.excess) * 0.4) : 0;
      s += `<circle class="halo" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(2 + halo).toFixed(1)}"/><circle class="mic${m.ok ? '' : ' off'}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2"><title>${esc(m.name)}${m.ok ? ` ${m.level} dBFS` : ': ' + esc(m.error || 'no audio')}</title></circle>`;
      s += `<text class="ml" x="${lx.toFixed(1)}" y="${(ly + 2).toFixed(1)}" text-anchor="${Math.abs(lx - x) < 3 ? 'middle' : lx > x ? 'start' : 'end'}">${esc(m.name)}</text>`;
    }
    return s;
  }

  _hot(st) { return new Set(st.active.filter((e) => e.method === 'adsb').map((e) => e.extra?.aircraft?.hex)); }

  /* ---------------------------------------------- schematic radar (log) */
  _radar(st) {
    const R_MICS = 26, R_NEAR = 44, R_IN = 58, R_OUT = 98, mi = this._mi;
    const unit = mi ? 1.609344 : 1, range = Math.max(2, this._c.range_km), label = mi ? 'mi' : 'km';
    const far = Math.max(1, ...st.mics.map((m) => m.distance));
    const km = (d) => R_IN + (R_OUT - R_IN) * Math.min(1, Math.log(Math.max(0.3, d) / 0.3) / Math.log(range / 0.3));
    const outer = Math.max(2, Math.round(range / unit));
    let s = `<svg viewBox="-112 -106 224 212" role="img" aria-label="Where sounds are coming from">`;
    s += `<circle class="ground" r="${R_IN - 4}"/>`;
    for (const d of [1, Math.round(outer / 2), outer].filter((d, i, a) => a.indexOf(d) === i)) {
      s += `<circle class="ring" r="${km(d * unit)}"/><text class="rl" x="3" y="${-km(d * unit) + 7}">${d} ${label}</text>`;
    }
    for (const [b, t] of [[0, 'N'], [90, 'E'], [180, 'S'], [270, 'W']]) {
      const [x, y] = polar(b, 104);
      s += `<text class="nesw" x="${x}" y="${y + 3}">${t}</text>`;
    }
    s += `<path class="house" d="M-7 4 V-3 L0 -9 L7 -3 V4 Z"/>`;
    s += this._sounds(st, R_IN - 4, R_NEAR);
    s += this._mics(st, (m) => {
      const r = 6 + (R_MICS - 6) * (m.distance / far);
      return [...polar(m.bearing, r), ...polar(m.bearing, r + 6)];
    });
    const hot = this._hot(st);
    for (const a of st.aircraft) {
      if (a.km > range * 1.15) continue;
      const on = hot.has(a.hex);
      const [x, y] = polar(on ? a.heard_bearing : a.bearing, km(on ? a.heard_km : a.km));
      s += this._plane(a, x, y, on, on || a.audible >= 0.25);
    }
    return s + '</svg>';
  }

  /* -------------------------------------------------- map radar (linear) */
  _tiles() {
    const el = this.shadowRoot.querySelector('.tiles'), m = this._meta;
    if (!el || !m || m.lat == null) return;
    const c = this._c, radius = Math.max(20, Number(c.map_radius_m) || 60);
    const [url, credit, maxZoom] = c.map_tiles ? [c.map_tiles, c.map_attribution || '', c.map_max_zoom || 19] : (TILES[c.map_style] || TILES.streets);
    const cosLat = Math.cos(m.lat * Math.PI / 180);
    const z = Math.max(1, Math.min(maxZoom, Math.floor(Math.log2(3.4 * 256 * 156543.03392 * cosLat / (2 * radius)))));
    const n = 2 ** z, span = (2 * radius) / (156543.03392 * cosLat / n) / 256;
    const cx = (m.lon + 180) / 360 * n;
    const cy = (1 - Math.asinh(Math.tan(m.lat * Math.PI / 180)) / Math.PI) / 2 * n;
    const x0 = cx - span / 2, y0 = cy - span / 2;
    let out = '';
    for (let ty = Math.floor(y0); ty <= Math.floor(y0 + span); ty++) {
      for (let tx = Math.floor(x0); tx <= Math.floor(x0 + span); tx++) {
        const src = url.replace('{z}', z).replace('{x}', ((tx % n) + n) % n).replace('{y}', ty);
        out += `<img alt="" loading="lazy" referrerpolicy="no-referrer" src="${esc(src)}" style="left:${((tx - x0) / span * 100).toFixed(3)}%;top:${((ty - y0) / span * 100).toFixed(3)}%;width:${(100 / span + 0.05).toFixed(3)}%">`;
      }
    }
    el.innerHTML = out;
    this.shadowRoot.querySelector('.credit').textContent = credit;
  }

  _mapPlot(st) {
    const R = 100, radius = Math.max(20, Number(this._c.map_radius_m) || 60), k = R / radius;
    let s = `<svg viewBox="-100 -100 200 200" role="img" aria-label="Where sounds are coming from, on a map">`;
    s += this._sounds(st, 150, 62);
    s += `<circle class="home" r="2.4"/>`;
    s += this._mics(st, (m) => {
      const r = Math.min(92, m.distance * k);
      return [...polar(m.bearing, r), ...polar(m.bearing, r + 6)];
    });
    const hot = this._hot(st);
    for (const a of st.aircraft) {
      const on = hot.has(a.hex), d = (on ? a.heard_km : a.km) * 1000 * k, b = on ? a.heard_bearing : a.bearing;
      if (d > 135 && !on && a.audible < 0.25) continue;      // off the map and not audible: leave it out
      const edge = d > 90;
      const [x, y] = polar(b, edge ? 88 : d);
      s += this._plane(a, x, y, on, edge ? 'far' : true);
    }
    /* scale bar */
    const bar = this._mi ? nice(radius * 0.5 * 3.28084) : nice(radius * 0.5);
    const len = (this._mi ? bar / 3.28084 : bar) * k;
    s += `<g class="scale" transform="translate(-94 92)"><path d="M0 -3 V0 H${len.toFixed(1)} V-3"/><text x="${(len / 2).toFixed(1)}" y="-3">${bar >= 5280 && this._mi ? +(bar / 5280).toFixed(1) + ' mi' : bar >= 1000 && !this._mi ? bar / 1000 + ' km' : bar + (this._mi ? ' ft' : ' m')}</text></g>`;
    s += `<g class="north" transform="translate(90 -86)"><path d="M0 -8 L4 4 L0 1.5 L-4 4 Z"/><text y="12">N</text></g>`;
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
      if (this._listening && cur) { /* stay put while someone is listening */ }
      else if (lead && ok.some((m) => m.id === lead)) this._auto = lead;
      else if (!cur || (best && best.excess > cur.excess + 4)) this._auto = best?.id || st.mics[0]?.id;
      shown = this._auto;
    }
    if (shown !== this._shown) {
      this._shown = shown;
      if (this._listening) this._listenStart();
    }
    this._set('.pills', `<span class="pill${this._mic ? '' : ' on'}" data-mic="">Auto</span>` +
      st.mics.map((m) => `<span class="pill${m.id === shown ? (this._mic ? ' on' : ' cur') : ''}${m.ok ? '' : ' off'}" data-mic="${esc(m.id)}">${esc(m.name)}</span>`).join(''));
    const secs = Math.min(this._meta.backlog_s, Math.max(10, this._c.spectrogram_seconds));
    const edges = this._meta.edges, lo = Math.log(edges[0]), hi = Math.log(edges[edges.length - 1]);
    this._set('.hz', [100, 300, 1000, 3000, 10000].filter((f) => f > edges[0] * 1.2 && f < edges[edges.length - 1] * 0.8)
      .map((f) => `<span style="bottom:${(Math.log(f) - lo) / (hi - lo) * 100}%">${f >= 1000 ? f / 1000 + ' kHz' : f + ' Hz'}</span>`).join(''));
    root.querySelector('.span').textContent = `last ${secs} s`;
    const t1 = this._specs?.[shown]?.t || st.now;
    const marks = [...st.active, ...st.recent].filter((e) => e.start > t1 - secs && (e.far || !e.mic || e.mic === shown));
    this._set('.marks', marks.map((e) => {
      const x = (1 - (t1 - e.start) / secs) * 100;
      return `<span class="g-${GROUP[e.cls] || 'road'}" style="left:${Math.max(0, x).toFixed(1)}%">${esc(e.label)}</span>`;
    }).join(''));
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

  /* ---------------------------------------------------------- live audio */
  _listenStart() {
    const mic = this._shown;
    if (!mic || !this._hass?.connection) return;
    this._listenStop(true);
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!this._audio) {
      this._audio = new Ctx();
      this._gain = this._audio.createGain();
      this._gain.connect(this._audio.destination);
    }
    this._audio.resume?.();
    this._playAt = 0;
    this._listening = mic;
    this._hearUnsub = this._hass.connection
      .subscribeMessage((m) => this._pcm(m), { type: 'soundscape/listen', mic })
      .catch(() => { this._listening = null; this._listenUi(); return null; });
    this._listenUi();
  }

  _listenStop(keepContext) {
    this._hearUnsub?.then((u) => u && u()).catch(() => {});
    this._hearUnsub = null;
    this._listening = null;
    if (!keepContext && this._audio) { this._audio.close?.(); this._audio = null; }
    if (this._built) this._listenUi();
  }

  _pcm(m) {
    if (m.type !== 'pcm' || !this._audio || m.mic !== this._listening) return;
    const bytes = b64(m.data), n = bytes.length >> 1;
    const pcm = new Int16Array(bytes.buffer, 0, n);
    const buf = this._audio.createBuffer(1, n, m.rate);
    const out = buf.getChannelData(0);
    for (let i = 0; i < n; i++) out[i] = pcm[i] / 32768;
    const src = this._audio.createBufferSource();
    src.buffer = buf;
    src.connect(this._gain);
    const now = this._audio.currentTime;
    if (this._playAt < now + 0.05 || this._playAt > now + 2) this._playAt = now + 0.25; // start, or resync after a stall
    src.start(this._playAt);
    this._playAt += buf.duration;
  }

  _listenUi() {
    const root = this.shadowRoot, hear = root?.querySelector('.hear');
    if (!hear) return;
    const on = !!this._listening;
    hear.classList.toggle('on', on);
    hear.title = on ? 'Stop listening' : 'Listen live';
    hear.firstElementChild.setAttribute('icon', on ? 'mdi:headphones-off' : 'mdi:headphones');
    const mute = root.querySelector('.mute'), vol = root.querySelector('.vol');
    mute.hidden = vol.hidden = !on;
    mute.firstElementChild.setAttribute('icon', this._muted || !this._volume ? 'mdi:volume-off' : 'mdi:volume-high');
    mute.title = this._muted ? 'Unmute' : 'Mute';
    if (this._gain) this._gain.gain.value = this._muted ? 0 : this._volume ** 2 * 4; // camera audio is quiet: up to +12 dB
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

  .radar { margin: 6px auto 0; max-width: 430px; position: relative; }
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
  .ev { cursor: pointer; }
  .ev circle { fill: var(--card-background-color, #fff); stroke: var(--g); stroke-width: 1.2; }
  .ev .ic { width: 12px; height: 12px; display: flex; align-items: center; justify-content: center; color: var(--g); --mdc-icon-size: 10px; }
  .ev ha-icon { display: flex; }
  .ev .el { text-anchor: middle; font-size: 4.8px; font-weight: 500; fill: var(--primary-text-color);
    paint-order: stroke; stroke: var(--card-background-color, #fff); stroke-width: 1.6px; stroke-linejoin: round; }
  .ev.old { opacity: .5; } .ev.old circle { stroke-width: .8; stroke-dasharray: 1.5 1.2; }
  .ev.old .ic { --mdc-icon-size: 8px; }
  .ac .body { fill: var(--secondary-text-color); opacity: .45; }
  .ac .detail { fill: none; stroke: var(--secondary-text-color); stroke-width: .7; opacity: .45; }
  .ac.near .body, .ac.near .detail { opacity: .9; }
  .ac.hot .body { fill: var(--air); opacity: 1; } .ac.hot .detail { stroke: var(--air); opacity: 1; }
  .ac text { font-size: 4.8px; } .ac.hot text { fill: var(--air); font-weight: 500; }
  .pulse { fill: none; stroke: var(--air); stroke-width: 1; animation: breathe 1.6s ease-in-out infinite; }
  @keyframes breathe { 0%, 100% { opacity: .15; } 50% { opacity: .6; } }

  .radar.map { aspect-ratio: 1; border-radius: 12px; overflow: hidden; background: #2a2d31; }
  .radar.map .tiles, .radar.map .plot { position: absolute; inset: 0; }
  .tiles img { position: absolute; display: block; height: auto; max-width: none; user-select: none; pointer-events: none; }
  .radar.map .tiles::after { content: ""; position: absolute; inset: 0; background: rgba(12,14,18,.28); }
  .radar.map svg { height: 100%; overflow: hidden; }
  .radar.map text { fill: #fff; paint-order: stroke; stroke: rgba(0,0,0,.75); stroke-width: 1.5px; stroke-linejoin: round; }
  .radar.map .mic { fill: #fff; stroke: #000; stroke-width: .5; } .radar.map .halo { fill: #4fc3f7; opacity: .45; }
  .radar.map .wedge { opacity: .34; }
  .radar.map .ev circle { fill: #fff; } .radar.map .ev .el { fill: #fff; stroke: rgba(0,0,0,.75); }
  .radar.map .ac .body { fill: #fff; opacity: .85; stroke: #000; stroke-width: .4; }
  .radar.map .ac .detail { stroke: #fff; opacity: .85; }
  .radar.map .ac.hot .body { fill: #4fc3f7; } .radar.map .ac.hot .detail { stroke: #4fc3f7; } .radar.map .ac.hot text { fill: #b3e5fc; }
  .home { fill: none; stroke: #fff; stroke-width: 1; }
  .scale path { fill: none; stroke: #fff; stroke-width: 1; } .scale text { text-anchor: middle; font-size: 5px; }
  .north path { fill: #fff; stroke: #000; stroke-width: .4; } .north text { text-anchor: middle; font-size: 6px; font-weight: 600; }
  .credit { position: absolute; right: 0; bottom: 0; padding: 1px 6px; font-size: 9px; color: #222; background: rgba(255,255,255,.7); border-top-left-radius: 6px; }

  .spec { margin-top: 10px; }
  .bar { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
  .pills, .filters { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
  .pill { font-size: 12px; padding: 2px 9px; border-radius: 10px; cursor: pointer; color: var(--secondary-text-color);
    border: 1px solid var(--divider-color); user-select: none; }
  .pill.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .pill.cur { border-color: var(--primary-color); color: var(--primary-text-color); }
  .pill.off { text-decoration: line-through; }
  .listen { display: flex; align-items: center; gap: 4px; flex: none; }
  .listen button { all: unset; cursor: pointer; width: 26px; height: 24px; display: grid; place-items: center; border-radius: 12px;
    color: var(--secondary-text-color); border: 1px solid var(--divider-color); --mdc-icon-size: 16px; }
  .listen button.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .listen [hidden] { display: none; }
  .vol { width: 84px; accent-color: var(--primary-color); }
  .frame { position: relative; border-radius: 8px; overflow: hidden; background: #000; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
  .hz span { position: absolute; left: 4px; transform: translateY(50%); font-size: 9.5px; color: rgba(255,255,255,.7); text-shadow: 0 0 3px #000; }
  .span { position: absolute; right: 6px; bottom: 3px; font-size: 9.5px; color: rgba(255,255,255,.6); text-shadow: 0 0 3px #000; }
  .marks span { position: absolute; top: 0; bottom: 0; border-left: 1px solid color-mix(in srgb, var(--g) 80%, #fff);
    padding: 2px 4px; font-size: 10.5px; font-weight: 500; color: #fff; text-shadow: 0 0 3px #000, 0 0 2px #000; white-space: nowrap; }

  .logwrap { margin-top: 10px; border-top: 1px solid var(--divider-color); padding-top: 8px; }
  .filters:not(:empty) { margin-bottom: 6px; }
  .filters .pill.on { background: var(--g, var(--primary-color)); border-color: var(--g, var(--primary-color)); }
  .log { overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--divider-color) transparent; padding-right: 2px; }
  .log::-webkit-scrollbar { width: 6px; } .log::-webkit-scrollbar-thumb { background: var(--divider-color); border-radius: 3px; }
  .row { display: grid; grid-template-columns: 58px 20px auto 1fr auto; gap: 8px; align-items: center; height: 28px; box-sizing: border-box; cursor: pointer; font-size: 13px; }
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
