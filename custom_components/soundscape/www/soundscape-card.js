/*
 * Soundscape card
 * What the microphones around the house hear, and where it is coming from.
 * Needs the Soundscape integration, which also loads this file.
 *
 *   type: custom:soundscape-card
 *   title: Soundscape
 *   show_icon: true           # the icon beside the title
 *   icon: mdi:waveform
 *   show_radar: true
 *   radar: schematic          # or: map (true scale), fisheye (map with logarithmic distance),
 *                             #     hyperbolic (the fisheye with a focus you can drag anywhere)
 *   aircraft: all             # or: audible (close enough to hear), heard (matched to a sound)
 *   map_style: streets        # or: satellite
 *   map_radius_m: 60          # how far the map reaches to start with (or map_radius_ft: 200)
 *   range_km: 10              # outer ring of the schematic radar (or range_mi: 6)
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
const VERSION = '0.7.1';

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

const DEFAULTS = {
  title: 'Soundscape', show_icon: true, icon: 'mdi:waveform', show_radar: true, radar: 'schematic', aircraft: 'all', map_style: 'streets', map_radius_m: 60,
  range_km: 10, radar_recent_seconds: 120, units: 'auto', show_spectrogram: true, mic: 'auto',
  spectrogram_height: 150, spectrogram_seconds: 60, show_listen: true, volume: 80,
  show_log: true, log_rows: 8, log_max: 100, log_hide: [],
};

/* Aircraft seen from above, nose up, in a box about 14 units wide. [filled outline, stroked detail] */
const PLANE = {
  jet: ['M0 -7 L1.3 -2.4 L7 3 L7 4.3 L1.3 2.4 L1 5.6 L3 6.9 L3 7.6 L-3 7.6 L-3 6.9 L-1 5.6 L-1.3 2.4 L-7 4.3 L-7 3 L-1.3 -2.4 Z', ''],
  propeller: ['M0 -6 L1.1 -2.8 L7.2 -2.3 L7.2 -0.5 L1.1 0 L0.8 5 L2.8 5.6 L2.8 6.6 L-2.8 6.6 L-2.8 5.6 L-0.8 5 L-1.1 0 L-7.2 -0.5 L-7.2 -2.3 L-1.1 -2.8 Z', 'M-2.6 -6.3 H2.6'],
  helicopter: ['M0 -3.6 C2.4 -3.6 2.4 2.2 0.7 2.8 L0.5 6.4 L2 6.4 L2 7.4 L-2 7.4 L-2 6.4 L-0.5 6.4 L-0.7 2.8 C-2.4 2.2 -2.4 -3.6 0 -3.6 Z', 'M-6.4 -0.6 A6.4 6.4 0 1 0 6.4 -0.6 A6.4 6.4 0 1 0 -6.4 -0.6 M-4.5 -5.1 L4.5 3.9 M-4.5 3.9 L4.5 -5.1'],
  tiltrotor: ['M0 -6 L1.1 -3.6 L1.1 -2 L6 -2 L6 -0.2 L1.1 -0.2 L1.1 4.4 L2.8 5.8 L2.8 6.6 L-2.8 6.6 L-2.8 5.8 L-1.1 4.4 L-1.1 -0.2 L-6 -0.2 L-6 -2 L-1.1 -2 L-1.1 -3.6 Z', 'M-9 -1.1 A3 3 0 1 0 -3 -1.1 A3 3 0 1 0 -9 -1.1 M3 -1.1 A3 3 0 1 0 9 -1.1 A3 3 0 1 0 3 -1.1'],
  aircraft: ['M0 -6 L4 5.5 L0 3 L-4 5.5 Z', ''],
};

/* [address, credit, deepest zoom, referrer policy] */
const SATELLITE = ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Imagery © Esri and its data providers', 19, null];
const OSM_CREDIT = '© OpenStreetMap contributors';
/* OpenStreetMap's servers want to know which page is asking. Home Assistant tells the browser not to
   say, so the tiles ask for the site's address (never the full page address) to be sent after all. */
const OSM_DIRECT = ['https://tile.openstreetmap.org/{z}/{x}/{y}.png', OSM_CREDIT, 19, 'origin'];

/* What "isolate" keeps for each kind of sound: the band it lives in, in Hz. Everything outside is dropped,
   and inside it only what rises above that microphone's steady background is kept. */
const ISOLATE = {
  bird: [1500, 11000], coyote: [300, 3000], dog: [250, 3500], cat: [300, 4500], voice: [100, 4000],
  vehicle: [80, 3000], horn: [300, 3500], machinery: [60, 4000], weather: [30, 2000],
  siren: [400, 4000], car_alarm: [800, 5000], glass: [2000, 11000], bang: [50, 4000], alarm: [1500, 5000],
  jet: [50, 2500], propeller: [50, 1200], helicopter: [30, 1500], tiltrotor: [30, 1500], aircraft: [50, 2500],
};

/* In-place radix-2 FFT of a real signal, sized once. */
function makeFFT(n) {
  const rev = new Uint32Array(n), cos = new Float32Array(n / 2), sin = new Float32Array(n / 2), bits = Math.log2(n);
  for (let i = 0; i < n; i++) { let r = 0; for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b); rev[i] = r; }
  for (let i = 0; i < n / 2; i++) { cos[i] = Math.cos(2 * Math.PI * i / n); sin[i] = Math.sin(2 * Math.PI * i / n); }
  return (re, im) => {
    for (let i = 0; i < n; i++) { const j = rev[i]; if (j > i) { const t = re[i]; re[i] = re[j]; re[j] = t; } im[i] = 0; }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1, step = n / size;
      for (let i = 0; i < n; i += size) {
        for (let j = 0, k = 0; j < half; j++, k += step) {
          const a = i + j, b = a + half, tr = re[b] * cos[k] + im[b] * sin[k], ti = im[b] * cos[k] - re[b] * sin[k];
          re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        }
      }
    }
  };
}

const TILE_CACHE = new Map();   // tiles being fetched for the fisheye views, shared by every card on the page
const TILE_DATA = new Map();    // their pixels once read, for redrawing while a drag is under way

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
  /* A new card gets every option written out at its default, in the household's units. */
  static getStubConfig(hass) {
    const mi = (hass || document.querySelector('home-assistant')?.hass)?.config?.unit_system?.length === 'mi';
    const { map_radius_m, range_km, ...rest } = DEFAULTS;
    return { ...rest, ...(mi ? { map_radius_ft: 200, range_mi: 6 } : { map_radius_m, range_km }) };
  }

  static getConfigForm() {
    const labels = {
      title: 'Title', show_icon: 'Title icon', icon: 'Icon', show_radar: 'Radar', show_spectrogram: 'Live spectrogram', show_log: 'Recent sounds',
      show_listen: 'Listen button', radar: 'Radar background', map_style: 'Map', map_radius_m: 'Map reaches',
      map_radius_ft: 'Map reaches', range_km: 'Schematic range for aircraft', range_mi: 'Schematic range for aircraft',
      radar_recent_seconds: 'Keep ended sounds on the radar', aircraft: 'Aircraft to draw',
      units: 'Distances', mic: 'Spectrogram microphone (auto, or a camera name)',
      spectrogram_height: 'Spectrogram height', spectrogram_seconds: 'Spectrogram span', volume: 'Starting volume',
      log_rows: 'Rows before the list scrolls', log_max: 'Rows kept', log_hide: 'Leave out of the list',
    };
    const mi = document.querySelector('home-assistant')?.hass?.config?.unit_system?.length === 'mi';
    const defaults = {
      title: 'Soundscape', show_icon: 'on', icon: 'mdi:waveform', radar: 'Schematic', aircraft: 'All nearby', map_style: 'Streets', map_radius_m: '60 m', map_radius_ft: '200 ft',
      range_km: '10 km', range_mi: '6 mi', radar_recent_seconds: '120 s (0 turns it off)',
      units: `Automatic (${mi ? 'miles and feet' : 'kilometres and metres'} here)`, mic: 'auto',
      spectrogram_height: '150 px', spectrogram_seconds: '60 s', volume: '80 %', log_rows: '8', log_max: '100',
      log_hide: 'nothing left out', show_radar: 'on', show_spectrogram: 'on', show_log: 'on', show_listen: 'on',
    };
    const num = (min, max, step, unit) => ({ number: { min, max, step, mode: 'box', ...(unit ? { unit_of_measurement: unit } : {}) } });
    const pick = (options) => ({ select: { mode: 'dropdown', options } });
    return {
      schema: [
        { name: 'title', selector: { text: {} } },
        { type: 'grid', name: '', schema: [
          { name: 'show_icon', selector: { boolean: {} } }, { name: 'icon', selector: { icon: {} } },
        ] },
        { type: 'grid', name: '', schema: [
          { name: 'show_radar', selector: { boolean: {} } }, { name: 'show_spectrogram', selector: { boolean: {} } },
          { name: 'show_log', selector: { boolean: {} } }, { name: 'show_listen', selector: { boolean: {} } },
        ] },
        { type: 'expandable', name: '', title: 'Radar and map', schema: [
          { type: 'grid', name: '', schema: [
            { name: 'radar', selector: pick([{ value: 'schematic', label: 'Schematic (logarithmic distance)' }, { value: 'map', label: 'Map (true scale)' }, { value: 'fisheye', label: 'Fisheye map (logarithmic distance)' }, { value: 'hyperbolic', label: 'Hyperbolic map (fisheye, drag to refocus)' }]) },
            { name: 'aircraft', selector: pick([{ value: 'all', label: 'All nearby' }, { value: 'audible', label: 'Close enough to hear' }, { value: 'heard', label: 'Only those heard' }]) },
            { name: 'map_style', selector: pick([{ value: 'streets', label: 'Streets' }, { value: 'satellite', label: 'Satellite' }]) },
            mi ? { name: 'map_radius_ft', selector: num(60, 60000, 10, 'ft') } : { name: 'map_radius_m', selector: num(20, 20000, 10, 'm') },
            mi ? { name: 'range_mi', selector: num(1, 30, 1, 'mi') } : { name: 'range_km', selector: num(2, 50, 1, 'km') },
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
      computeHelper: (s) => (defaults[s.name] ? `Default: ${defaults[s.name]}` : undefined),
    };
  }

  setConfig(config) {
    this._config = config;   // card-mod and UIX look here for their own keys
    this._c = { ...DEFAULTS, ...Object.fromEntries(Object.entries(config).filter(([, v]) => v !== null && v !== '')) };
    if (this._c.range_mi != null) this._c.range_km = this._c.range_mi * 1.609344;
    this._view = null;
    this._focus = { e: 0, n: 0 };   // where the hyperbolic map is centred, metres east and north of the house
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

  constructor() {
    super();
    /* Built once, here, and never replaced: card-mod and UIX put their styles into this shadow root
       as soon as the card is created, and would lose them if it were rebuilt. */
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="root"></div></ha-card>`;
  }

  connectedCallback() { this._subscribe(); }

  disconnectedCallback() {
    this._unsub?.then((u) => u && u()).catch(() => {});
    this._unsub = null;
    this._listenStop();
    this._clipStop();
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
    } else if (m.type === 'meta') {
      this._meta = m.meta;
      if (this._view) this._view.ox = this._view.oy = 0;
      this._viewSave();
      this._tiles();
      if (this._isFish) this._fishRender();
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
      this._specs[mic] = { canvas, ctx, t: 0, raw: new Uint8Array(w * this._meta.bands), lo: 40, hi: 200, due: 0 };
    }
    return this._specs[mic];
  }

  _push(mic, bytes, t) {
    const s = this._spec(mic), bands = this._meta.bands;
    let n = Math.floor(bytes.length / bands);
    if (!n) return;
    const w = s.canvas.width;
    if (n > w) { bytes = bytes.subarray((n - w) * bands); n = w; }
    s.raw.copyWithin(0, n * bands);
    s.raw.set(bytes.subarray(0, n * bands), (w - n) * bands);
    s.t = t;
    s.due -= n;
    if (s.due <= 0 && this._contrast(s)) return;      // range moved: everything was redrawn
    s.ctx.globalCompositeOperation = 'copy';
    s.ctx.drawImage(s.canvas, -n, 0);
    s.ctx.globalCompositeOperation = 'source-over';
    this._draw(s, w - n, n);
  }

  _draw(s, x0, n) {
    const bands = this._meta.bands, img = s.ctx.createImageData(n, bands), k = 255 / (s.hi - s.lo);
    for (let x = 0; x < n; x++) {
      const col = (x0 + x) * bands;
      for (let b = 0; b < bands; b++) {
        const v = Math.max(0, Math.min(255, Math.round((s.raw[col + b] - s.lo) * k))) * 4, o = ((bands - 1 - b) * n + x) * 4;
        img.data[o] = LUT[v]; img.data[o + 1] = LUT[v + 1]; img.data[o + 2] = LUT[v + 2]; img.data[o + 3] = 255;
      }
    }
    s.ctx.putImageData(img, x0, 0);
  }

  /* Cameras differ a great deal in level. Fit the colour range to the quiet and loud ends of the last 90 s. */
  _contrast(s) {
    s.due = Math.round(this._meta.cols_per_s * 5);
    const hist = new Uint32Array(256);
    let total = 0;
    for (let i = 0; i < s.raw.length; i += 5) { const v = s.raw[i]; if (v) { hist[v]++; total++; } }
    if (total < 500) return false;
    const at = (q) => { let acc = 0; for (let v = 1; v < 256; v++) { acc += hist[v]; if (acc >= total * q) return v; } return 255; };
    const lo = Math.max(0, at(0.08) - 6), hi = Math.min(255, Math.max(at(0.997) + 10, lo + 90));
    if (Math.abs(lo - s.lo) < 8 && Math.abs(hi - s.hi) < 8) return false;
    s.lo = lo; s.hi = hi;
    this._draw(s, 0, s.canvas.width);
    return true;
  }

  get _isFish() { return this._c.radar === 'fisheye' || this._c.radar === 'hyperbolic'; }

  /* --------------------------------------------------------------- units */
  get _mi() { return (this._c.units === 'auto' ? this._meta?.units : this._c.units) === 'mi'; }

  _dist(km) {
    if (this._mi) { const mi = km / 1.609344; return mi >= 0.1 ? `${mi.toFixed(1)} mi` : `${Math.round(km * 328.084) * 10} ft`; }
    return km >= 0.1 ? `${km.toFixed(1)} km` : `${Math.round(km * 100) * 10} m`;
  }

  /* -------------------------------------------------------------- render */
  _build() {
    const c = this._c, fish = this._isFish, map = c.radar === 'map' || fish;
    this.shadowRoot.querySelector('.root').innerHTML = `
        <div class="head">${c.show_icon && c.icon ? `<ha-icon class="ticon" icon="${esc(c.icon)}"></ha-icon>` : ''}<span class="title"></span><span class="status"></span></div>
        <div class="body">
        <div class="now"></div>
        <div class="why" hidden><div class="whytext"></div><div class="fbslot"></div></div>
        <div class="clip" hidden>
          <div class="cbar">
            <button class="cplay" title="Play the recording as the microphone heard it"><ha-icon icon="mdi:play"></ha-icon></button>
            <button class="ciso" title="Show only this sound: its frequency band, with the steady background removed"><ha-icon icon="mdi:filter-variant"></ha-icon><span>Isolate</span></button>
            <button class="ctext" title="Put the speech in this recording into words" hidden><ha-icon icon="mdi:text-recognition"></ha-icon><span>Transcribe</span></button>
            <ha-icon class="cvolicon" icon="mdi:volume-high"></ha-icon>
            <input class="cvol" type="range" min="0" max="100" step="1" value="${Math.round(this._volume * 100)}" title="Playback volume">
            <span class="cinfo"></span>
          </div>
          <div class="ctrans" hidden></div>
          <div class="cframe" hidden><canvas class="cspec"></canvas><div class="cmarks"></div><div class="ccursor" hidden></div></div>
        </div>
        ${c.show_radar ? `<div class="radar${map ? ' map' : ''}${fish ? ' fish' : ''}${c.radar === 'hyperbolic' ? ' hyper' : ''}">${fish ? '<canvas class="warp"></canvas><div class="note" hidden></div>' : map ? '<div class="tiles"></div>' : ''}<div class="plot"></div>${map ? `<div class="credit"></div>
          <div class="mapctl"><button data-zoom="0.625" title="Zoom in">+</button><button data-zoom="1.6" title="Zoom out">&minus;</button>
            <button class="recenter" title="Back to the house and the starting zoom"><ha-icon icon="mdi:home-outline"></ha-icon></button>
            <button class="sethome" title="The house is here: save the middle of the map as the house" hidden${fish ? ' style="display:none"' : ''}><ha-icon icon="mdi:map-marker-check-outline"></ha-icon></button></div>` : ''}</div>` : ''}
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
        </div>`;
    const root = this.shadowRoot;
    root.querySelector('.title').textContent = c.title || '';
    if (!this._wired) {
      this._wired = true;
      root.addEventListener('click', (e) => {
        const hit = (sel) => e.target.closest(sel);
        if (hit('.hear')) { this._listening ? this._listenStop() : this._listenStart(); return; }
        if (hit('.mute')) { this._muted = !this._muted; this._listenUi(); return; }
        if (hit('.cplay')) { this._play ? this._clipStop() : this._clipPlay(0); return; }
        if (hit('.ciso')) { this._clipIsolate(!this._iso); return; }
        if (hit('.ctext')) { this._transcribe(this._clipId); return; }
        const fbb = hit('[data-fb]');
        if (fbb) { this._answer(fbb.dataset.fb); return; }
        const fbr = hit('.fbreset');
        if (fbr) {
          this._hass.callWS({ type: 'soundscape/feedback_reset', cls: fbr.dataset.cls, mic: fbr.dataset.mic || null })
            .catch((err) => console.warn('Soundscape: could not reset', err));
          return;
        }
        if (hit('.fbwas')) return;
        const strip = hit('.cframe');
        if (strip && this._clip) { const b = strip.getBoundingClientRect(); this._clipPlay((e.clientX - b.left) / b.width * this._clip.seconds); return; }
        if (Date.now() - (this._dragged || 0) < 250) return;      // the end of a drag is not a click
        const zoom = hit('[data-zoom]');
        if (zoom && this._isFish) { this._fishZoom(Number(zoom.dataset.zoom)); return; }
        if (zoom) { this._zoom(Number(zoom.dataset.zoom)); return; }
        if (hit('.recenter') && this._isFish) { this._fish = null; this._focus = { e: 0, n: 0 }; try { localStorage.removeItem('soundscape-card-fisheye'); } catch (e) { /* private mode */ } this._fishZoom(1); return; }
        if (hit('.recenter')) { this._view = { radius: this._radius0(), ox: 0, oy: 0 }; this._viewChanged(); return; }
        if (hit('.sethome')) { this._setHome(); return; }
        const pill = hit('[data-mic]');
        if (pill) { this._mic = pill.dataset.mic || null; this._render(); return; }
        const filter = hit('[data-filter]');
        if (filter) { this._filter = filter.dataset.filter || null; this._render(); return; }
        const ev = hit('[data-ev]');
        if (ev) { this._open = this._open === ev.dataset.ev ? null : ev.dataset.ev; this._render(); }
      });
      root.addEventListener('change', (e) => {
        if (e.target.classList?.contains('fbwas') && e.target.value) this._answer('wrong', e.target.value);
      });
      root.addEventListener('input', (e) => {
        const cl = e.target.classList;
        if (cl?.contains('vol') || cl?.contains('cvol')) {      // one volume for live listening and for recordings
          this._volume = e.target.value / 100;
          if (cl.contains('vol')) this._muted = false;
          for (const el of root.querySelectorAll('.vol, .cvol')) if (el !== e.target) el.value = e.target.value;
          this._listenUi();
        }
      });
    }
    this._canvas = root.querySelector('.frame canvas');
    if (this._canvas) {
      this._ro = this._ro || new ResizeObserver(() => this._paint());
      this._ro.observe(this._canvas);
    }
    if (fish) this._fishSetup(root.querySelector('.radar'));
    else if (map) { this._tiles(); this._mapGestures(root.querySelector('.radar')); }
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
      this.shadowRoot.querySelector('.root').innerHTML = `<div class="empty">Soundscape is not answering: ${esc(this._error)}.<br>Is the Soundscape integration set up?</div>`;
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
      this._set('.whytext', `<b>${esc(open.label)}</b> · ${Math.round(open.conf * 100)}% · ${clock(open.start)}<ul>${lines.join('')}${disp.join('')}</ul>${this._levels(open)}`);
      // its own element, so a list that is open is not closed by the panel refreshing every second
      const slot = why.querySelector('.fbslot'), fbHtml = this._feedback(open, st);
      if (!slot.firstChild || slot.dataset.sig !== fbHtml) { slot.dataset.sig = fbHtml; slot.innerHTML = fbHtml; }
    }

    this._clipUi(open);
    if (this._c.show_radar && this._c.radar !== 'schematic') this._source();   // renews the street tiles' token when due
    if (this._c.show_radar) this._set('.plot', this._c.radar === 'map' ? this._mapPlot(st) : this._isFish ? this._fishPlot(st) : this._radar(st));
    if (this._c.show_spectrogram) this._specUi(st);
    if (this._c.show_log) this._log(st);
  }

  /* Right, wrong, or what it really was: each answer tunes this kind of sound at this microphone. */
  _feedback(ev, st) {
    const classes = this._meta?.classes;
    if (!classes || !classes[ev.cls] || this._meta.learn === false) return '';     // switched off in the integration
    const fb = this._fbPending?.id === ev.id ? this._fbPending : ev.extra?.feedback || {};
    const air = ['jet', 'propeller', 'helicopter', 'tiltrotor', 'aircraft'].includes(ev.cls);
    const mic = air ? null : ev.mic;
    const micName = mic ? (st.mics.find((m) => m.id === mic)?.name || mic) : null;
    const opts = Object.entries(classes).filter(([k]) => k !== ev.cls)
      .map(([k, [label]]) => `<option value="${k}"${fb.actual === k ? ' selected' : ''}>${esc(label)}</option>`).join('');
    const right = fb.verdict === 'right', wrong = fb.verdict === 'wrong' && !fb.actual;
    const cal = (st.calibration || []).find((c) => c.cls === ev.cls && (c.mic || null) === mic);
    const kind = (classes[ev.cls][0] || ev.cls).toLowerCase();
    const where = micName ? `${kind} at ${esc(micName)}` : (air ? 'aircraft' : kind);
    let note = '';
    if (cal) {
      const n = (k, w) => `${cal[k]} ${w}`;
      note = `<div class="fbnote">From your answers, ${where} needs ${cal.factor < 1 ? 'more' : 'less'} evidence: confidence is ${Math.round(cal.factor * 100)}% of normal (${n('wrong', 'wrong')}, ${n('right', 'right')}).`
        + `${this._hass?.user?.is_admin !== false ? ` <a class="fbreset" data-cls="${ev.cls}" data-mic="${mic ?? ''}">Reset</a>` : ''}</div>`;
    }
    return `<div class="fb"><span class="fbq">Was this right?</span>
      <button data-fb="right" class="${right ? 'on' : ''}" title="Yes: this kind of sound at this microphone is reported a little more readily"><ha-icon icon="mdi:check"></ha-icon><span>Right</span></button>
      <button data-fb="wrong" class="${wrong ? 'on bad' : ''}" title="No: this kind of sound at this microphone needs more evidence from now on"><ha-icon icon="mdi:close"></ha-icon><span>Wrong</span></button>
      <select class="fbwas${fb.actual ? ' on' : ''}" title="Wrong, and this is what it was"><option value="">It was…</option>${opts}</select>
      </div>${note}`;
  }

  async _answer(verdict, actual = null) {
    const id = Number(this._open);
    if (!id) return;
    const cur = [...(this._state?.active || []), ...(this._state?.recent || [])].find((e) => e.id === id)?.extra?.feedback || {};
    if (cur.verdict === verdict && (cur.actual || null) === actual) verdict = null;     // a second press takes it back
    this._fbPending = { id, verdict, actual };
    this._render();
    try {
      await this._hass.callWS({ type: 'soundscape/feedback', event: id, verdict, ...(actual ? { actual } : {}) });
    } catch (err) {
      console.warn('Soundscape: the answer was not saved', err);
    }
    this._fbPending = null;
    this._render();
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
  _sounds(st, rWedge, rIcon, proj) {
    let s = '';
    const keep = Number(this._c.radar_recent_seconds) || 0, used = [];
    const at = proj || polar;   // (bearing from the house, radius in drawing units) -> x, y
    const spot = (bearing, r) => { // nudge icons that would land on top of each other
      let rr = r;
      while (used.some(([b, q]) => Math.abs(((b - bearing + 540) % 360) - 180) < 22 && Math.abs(q - rr) < 14)) rr -= 15;
      used.push([bearing, rr]);
      let [x, y] = at(bearing, Math.max(14, rr));
      if (proj) {   // far from the focus the house shrinks to a dot: fan the icons out beside it
        const free = (px, py) => !placed.some(([qx, qy]) => Math.hypot(px - qx, py - qy) < 15);
        const [ox, oy] = [x, y];
        for (let i = 1; !free(x, y) && i < 12; i++) { const a = i * 2.4, d = 9 + i * 5; x = ox + d * Math.cos(a); y = oy + d * Math.sin(a); }
        placed.push([x, y]);
      }
      return [x, y];
    };
    const placed = [];
    const [h0x, h0y] = at(0, 0), [i0x, i0y] = at(0, rIcon);
    const squeezed = proj && Math.hypot(i0x - h0x, i0y - h0y) < 10;   // the house is far from the focus
    for (const e of st.active) {
      if (e.method === 'adsb') continue;
      const g = GROUP[e.cls] || 'road';
      if (e.far || e.bearing == null) {
        const [hx, hy] = at(0, 0);
        s += `<circle class="far g-${g}" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="${rIcon + 6}"/>`;
        const [x, y] = spot(315, rIcon + 6);
        s += this._sound(e, x, y, false);
        continue;
      }
      if (proj) {   // the wedge bends with the map: trace its edge point by point
        const pts = [at(0, 0)];
        for (let a = -24; a <= 24; a += 6) pts.push(at(e.bearing + a, rWedge));
        s += `<path class="wedge g-${g}" d="M${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L')} Z"/>`;
      } else {
        const [x1, y1] = polar(e.bearing - 24, rWedge), [x2, y2] = polar(e.bearing + 24, rWedge);
        s += `<path class="wedge g-${g}" d="M0 0 L${x1.toFixed(1)} ${y1.toFixed(1)} A${rWedge} ${rWedge} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z"/>`;
      }
      const [x, y] = spot(e.bearing, rIcon);
      s += this._sound(e, x, y, false);
    }
    if (keep && !squeezed) {
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
    const spots = st.mics.map((m) => place(m)), n = spots.length || 1;
    const mx = spots.reduce((t, q) => t + q[0], 0) / n, my = spots.reduce((t, q) => t + q[1], 0) / n;
    const spread = n < 2 ? 99 : Math.max(0, ...spots.map((q) => Math.hypot(q[0] - mx, q[1] - my))) * 2;
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

  /* all nearby, only those close enough to hear, or only those matched to a sound */
  _planes(st, hot) {
    const mode = this._c.aircraft;
    return st.aircraft.filter((a) => hot.has(a.hex) || mode === 'all' || !mode || (mode === 'audible' && a.audible >= 0.25));
  }

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
    for (const a of this._planes(st, hot)) {
      if (a.km > range * 1.15) continue;
      const on = hot.has(a.hex);
      const [x, y] = polar(on ? a.heard_bearing : a.bearing, km(on ? a.heard_km : a.km));
      s += this._plane(a, x, y, on, on || a.audible >= 0.25);
    }
    return s + '</svg>';
  }

  /* -------------------------------------------------- map radar (linear) */
  _radius0() {
    const c = this._c;
    return Math.max(15, c.map_radius_ft != null ? c.map_radius_ft * 0.3048 : Number(c.map_radius_m) || 60);
  }

  /* What the map shows: how far it reaches, and how far its middle is from the house (metres east, north).
     Zooming and dragging are remembered in this browser until the card's own setting is changed. */
  _viewGet() {
    if (!this._view) {
      let saved = {};
      try { saved = JSON.parse(localStorage.getItem('soundscape-card-view') || '{}'); } catch (e) { /* private mode */ }
      const fresh = saved.from === this._radius0() && saved.radius > 0;
      this._view = { radius: fresh ? saved.radius : this._radius0(), ox: fresh ? saved.ox || 0 : 0, oy: fresh ? saved.oy || 0 : 0 };
    }
    return this._view;
  }

  _viewSave() {
    try { localStorage.setItem('soundscape-card-view', JSON.stringify({ ...this._viewGet(), from: this._radius0() })); } catch (e) { /* private mode */ }
  }

  _viewChanged() {
    const v = this._viewGet();
    v.radius = Math.min(40000, Math.max(15, v.radius));
    this._viewSave();
    this._tiles();
    delete this._sig['.plot'];
    if (this._state) this._render();
  }

  _zoom(factor) { this._viewGet().radius *= factor; this._viewChanged(); }

  async _setHome() {
    const v = this._viewGet(), m = this._meta;
    const lat = m.lat + v.oy / 111320, lon = m.lon + v.ox / (111320 * Math.cos(m.lat * Math.PI / 180));
    try {
      await this._hass.callWS({ type: 'soundscape/set_home', lat, lon });
    } catch (err) {
      const b = this.shadowRoot.querySelector('.sethome');
      if (b) b.title = `Could not save: ${err?.message || err}`;
    }
  }

  _mapGestures(el) {
    const pts = new Map();
    let start = null, moved = false;
    const layers = () => [el.querySelector('.tiles'), el.querySelector('.plot')];
    const shift = (dx, dy, scale) => { for (const l of layers()) l.style.transform = dx || dy || scale !== 1 ? `translate(${dx}px, ${dy}px) scale(${scale})` : ''; };
    const spread = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
    el.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.mapctl')) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      start = { x: e.clientX, y: e.clientY, spread: pts.size === 2 ? spread() : 0 };
      moved = false;
    });
    el.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId) || !start) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 2 && start.spread) { moved = true; shift(0, 0, spread() / start.spread); return; }
      const dx = e.clientX - start.x, dy = e.clientY - start.y;
      if (!moved && Math.hypot(dx, dy) < 5) return;
      if (!moved) { moved = true; el.setPointerCapture?.(e.pointerId); }
      shift(dx, dy, 1);
    });
    const end = (e) => {
      if (!pts.has(e.pointerId)) return;
      const v = this._viewGet(), perPx = 2 * v.radius / el.clientWidth;
      if (moved && pts.size === 2 && start?.spread) v.radius /= spread() / start.spread;
      else if (moved && start) { v.ox -= (e.clientX - start.x) * perPx; v.oy += (e.clientY - start.y) * perPx; }
      pts.delete(e.pointerId);
      if (moved) { this._dragged = Date.now(); shift(0, 0, 1); this._viewChanged(); }
      start = null; moved = false;
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    el.addEventListener('wheel', (e) => {
      e.preventDefault();
      this._viewGet().radius *= e.deltaY > 0 ? 1.25 : 0.8;
      clearTimeout(this._wheel);
      this._wheel = setTimeout(() => this._viewChanged(), 60);
    }, { passive: false });
  }

  /* Street tiles come through Home Assistant's own map proxy where this version has one: nothing is
     asked of an outside server by the browser, and the fisheye view can always read them. Otherwise
     straight from OpenStreetMap. The proxy's token is renewed well inside its half-hour life. */
  _source() {
    const c = this._c;
    if (c.map_tiles) return [c.map_tiles, c.map_attribution || '', c.map_max_zoom || 19, c.map_referrer || null];
    if (c.map_style === 'satellite') return SATELLITE;
    if (!(this._street && Date.now() - this._street.at < 20 * 60 * 1000) && !this._streetBusy && this._hass) {
      this._streetBusy = true;
      const first = !this._street;
      this._hass.callWS({ type: 'map_tiles/access_token' }).then((r) => {
        if (!r?.token) throw new Error('no token');
        const base = this._hass.hassUrl ? this._hass.hassUrl('/api/map_tiles') : '/api/map_tiles';
        return [`${base}/raster/{z}/{x}/{y}.png?token=${encodeURIComponent(r.token)}`, OSM_CREDIT, 19, null];
      }).catch(() => OSM_DIRECT).then((src) => {
        this._street = { at: Date.now(), src };
        this._streetBusy = false;
        this._tiles();
        if (first && this._isFish) this._fishRender();
      });
    }
    return this._street?.src || null;
  }

  _tiles() {
    const el = this.shadowRoot?.querySelector('.tiles'), m = this._meta, src = this._source();
    if (!el || !m || m.lat == null || !src) return;
    const v = this._viewGet(), radius = v.radius;
    const [url, credit, maxZoom, referrer] = src;
    const cosLat = Math.cos(m.lat * Math.PI / 180);
    const lat = m.lat + v.oy / 111320, lon = m.lon + v.ox / (111320 * cosLat);
    const z = Math.max(1, Math.min(maxZoom, Math.floor(Math.log2(3.4 * 256 * 156543.03392 * cosLat / (2 * radius)))));
    const n = 2 ** z, span = (2 * radius) / (156543.03392 * cosLat / n) / 256;
    const cx = (lon + 180) / 360 * n;
    const cy = (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n;
    const x0 = cx - span / 2, y0 = cy - span / 2;
    let out = '';
    for (let ty = Math.floor(y0); ty <= Math.floor(y0 + span); ty++) {
      for (let tx = Math.floor(x0); tx <= Math.floor(x0 + span); tx++) {
        const src = url.replace('{z}', z).replace('{x}', ((tx % n) + n) % n).replace('{y}', ty);
        out += `<img alt="" draggable="false"${referrer ? ` referrerpolicy="${referrer}"` : ''} src="${esc(src)}" style="left:${((tx - x0) / span * 100).toFixed(3)}%;top:${((ty - y0) / span * 100).toFixed(3)}%;width:${(100 / span + 0.05).toFixed(3)}%">`;
      }
    }
    if (this._tileSig !== out) { this._tileSig = out; el.innerHTML = out; }
    this.shadowRoot.querySelector('.credit').textContent = credit;
    const moved = Math.hypot(v.ox, v.oy) > 1.5;
    const pin = this.shadowRoot.querySelector('.sethome');
    if (pin) pin.hidden = !(moved && this._hass?.user?.is_admin !== false);
  }

  _mapPlot(st) {
    const v = this._viewGet(), radius = v.radius, k = 100 / radius;
    const hx = -v.ox * k, hy = v.oy * k;                      // where the house sits in the view
    const far = Math.max(1, ...st.mics.map((m) => m.distance));
    const rIcon = Math.min(62, Math.max(20, (far + 12) * k)); // just outside the microphones, at true scale when zoomed in
    let s = `<svg viewBox="-100 -100 200 200" role="img" aria-label="Where sounds are coming from, on a map">`;
    s += `<g transform="translate(${hx.toFixed(1)} ${hy.toFixed(1)})">`;
    s += this._sounds(st, rIcon + 16, rIcon);
    s += `<circle class="home" r="2.4"/>`;
    s += this._mics(st, (m) => [...polar(m.bearing, m.distance * k), ...polar(m.bearing, m.distance * k + 6)]);
    s += '</g>';
    if (Math.hypot(hx, hy) > 2) s += '<path class="cross" d="M-5 0 H5 M0 -5 V5"/>';
    const hot = this._hot(st);
    for (const a of this._planes(st, hot)) {
      const on = hot.has(a.hex), d = (on ? a.heard_km : a.km) * 1000 * k, b = on ? a.heard_bearing : a.bearing;
      let [x, y] = polar(b, d);
      x += hx; y += hy;
      const out = Math.max(Math.abs(x), Math.abs(y));
      if (out > 140 && !on && a.audible < 0.25) continue;     // off the map and not audible: leave it out
      const edge = out > 90;
      if (edge) { x *= 88 / out; y *= 88 / out; }
      s += this._plane(a, x, y, on, edge ? 'far' : true);
    }
    /* scale bar */
    const bar = this._mi ? nice(radius * 0.5 * 3.28084) : nice(radius * 0.5);
    const len = (this._mi ? bar / 3.28084 : bar) * k;
    s += `<g class="scale" transform="translate(-94 92)"><path d="M0 -3 V0 H${len.toFixed(1)} V-3"/><text x="${(len / 2).toFixed(1)}" y="-3">${bar >= 5280 && this._mi ? +(bar / 5280).toFixed(1) + ' mi' : bar >= 1000 && !this._mi ? bar / 1000 + ' km' : bar + (this._mi ? ' ft' : ' m')}</text></g>`;
    s += `<g class="north" transform="translate(90 -86)"><path d="M0 -8 L4 4 L0 1.5 L-4 4 Z"/><text y="12">N</text></g>`;
    return s + '</svg>';
  }

  /* ------------------------------------------- fisheye map (logarithmic) */
  /* Distance d metres from the house is drawn at a fraction u of the radius, d = c (e^(k u) - 1):
     close to true scale in the middle, logarithmic further out. Bearings are never bent.
     The configured map reach lands at 30 % of the radius and the aircraft range at the rim. */
  _fishGet() {
    if (!this._fish) {
      const base = Math.max(500, this._c.range_km * 1000);
      let saved = {};
      try { saved = JSON.parse(localStorage.getItem('soundscape-card-fisheye') || '{}'); } catch (e) { /* private mode */ }
      const range = saved.from === base && saved.range > 0 ? saved.range : base;
      const inner = Math.min(this._radius0(), range / 5);
      let lo = 0.01, hi = 40;
      for (let i = 0; i < 60; i++) {
        const k = (lo + hi) / 2;
        if ((Math.exp(k) - 1) / (Math.exp(0.3 * k) - 1) < range / inner) lo = k; else hi = k;
      }
      const k = (lo + hi) / 2;
      this._fish = { range, base, k, c: range / (Math.exp(k) - 1) };
    }
    return this._fish;
  }

  _fishU(metres) { const f = this._fishGet(); return Math.min(1.2, Math.log(Math.max(0, metres) / f.c + 1) / f.k); }

  _fishZoom(factor) {
    const f = this._fishGet(), range = Math.min(80000, Math.max(300, f.range * factor));
    try { localStorage.setItem('soundscape-card-fisheye', JSON.stringify({ range, from: f.base })); } catch (e) { /* private mode */ }
    this._fish = null;
    delete this._sig['.plot'];
    if (this._state) this._render();
    clearTimeout(this._fishTimer);
    this._fishTimer = setTimeout(() => this._fishRender(), 150);
  }

  /* Metres from the focus for a point of the drawing (x right, y down, rim at 98). */
  _fishGround(x, y) {
    const f = this._fishGet(), r = Math.hypot(x, y);
    if (r < 1e-6) return [0, 0];
    const d = f.c * (Math.exp(f.k * Math.min(1, r / 98)) - 1);
    return [d * x / r, -d * y / r];
  }

  /* The drawing position of a point given in metres east and north of the house. */
  _fishPoint(east, north) {
    const de = east - this._focus.e, dn = north - this._focus.n, d = Math.hypot(de, dn);
    if (d < 1e-6) return [0, 0, 0];
    const u = this._fishU(d), r = 98 * Math.min(u, 1);
    return [r * de / d, -r * dn / d, u];
  }

  _fishSetup(el) {
    this._fishRo = this._fishRo || new ResizeObserver(() => { clearTimeout(this._fishTimer); this._fishTimer = setTimeout(() => this._fishRender(), 200); });
    this._fishRo.observe(el);
    el.addEventListener('wheel', (e) => { e.preventDefault(); this._fishZoom(e.deltaY > 0 ? 1.25 : 0.8); }, { passive: false });
    if (this._c.radar !== 'hyperbolic') return;
    /* Drag: the place under the finger stays under the finger, so pulling a spot to the middle magnifies it. */
    let grab = null, moved = false, frame = 0;
    const here = (e) => { const b = el.getBoundingClientRect(); return [((e.clientX - b.left) / b.width - 0.5) * 200, ((e.clientY - b.top) / b.height - 0.5) * 200]; };
    el.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.mapctl')) return;
      const [x, y] = here(e), [ge, gn] = this._fishGround(x, y);
      grab = { e: this._focus.e + ge, n: this._focus.n + gn, x, y };
      moved = false;
    });
    el.addEventListener('pointermove', (e) => {
      if (!grab) return;
      const [x, y] = here(e);
      if (!moved && Math.hypot(x - grab.x, y - grab.y) < 2.5) return;
      if (!moved) { moved = true; el.setPointerCapture?.(e.pointerId); el.classList.add('dragging'); }
      const [ge, gn] = this._fishGround(x, y);
      const limit = this._fishGet().range * 1.5;
      this._focus = { e: Math.max(-limit, Math.min(limit, grab.e - ge)), n: Math.max(-limit, Math.min(limit, grab.n - gn)) };
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; delete this._sig['.plot']; if (this._state) this._render(); this._fishRender(true); });
    });
    const end = () => {
      if (!grab) return;
      grab = null;
      el.classList.remove('dragging');
      if (moved) { this._dragged = Date.now(); delete this._sig['.plot']; if (this._state) this._render(); this._fishRender(); }
      moved = false;
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
  }

  _tile(z, x, y, url, referrer) {
    const key = `${url.split('?')[0]}|${z}/${x}/${y}`;
    if (!TILE_CACHE.has(key)) {
      TILE_CACHE.set(key, new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';           // needed to read the pixels back
        if (referrer) img.referrerPolicy = referrer;
        img.onload = () => {
          try {
            const cv = document.createElement('canvas');
            cv.width = cv.height = 256;
            const ctx = cv.getContext('2d', { willReadFrequently: true });
            ctx.drawImage(img, 0, 0, 256, 256);
            const data = ctx.getImageData(0, 0, 256, 256).data;
            TILE_DATA.set(key, data);
            if (TILE_DATA.size > 220) TILE_DATA.delete(TILE_DATA.keys().next().value);
            resolve(data);
          } catch (e) { resolve(null); }
        };
        img.onerror = () => resolve(null);
        img.src = url.replace('{z}', z).replace('{x}', x).replace('{y}', y);
      }));
      if (TILE_CACHE.size > 220) TILE_CACHE.delete(TILE_CACHE.keys().next().value);
    }
    return TILE_CACHE.get(key);
  }

  /* preview: while dragging. Small, and drawn at once from whatever tiles are already here. */
  async _fishRender(preview) {
    const cv = this.shadowRoot?.querySelector('canvas.warp'), m = this._meta;
    if (!cv || !m || m.lat == null || !cv.clientWidth) return;
    const f = this._fishGet(), src = this._source();
    if (!src) return;                                                   // street source still being worked out
    const [url, credit, maxZoom, referrer] = src;
    const run = this._fishRun = (this._fishRun || 0) + 1;
    this.shadowRoot.querySelector('.credit').textContent = credit;
    const S = preview ? 280 : Math.min(760, Math.round(cv.clientWidth * Math.min(2, window.devicePixelRatio || 1))), half = S / 2;
    const fe = this._focus.e, fn = this._focus.n, stem = url.split('?')[0];
    const cosLat = Math.cos(m.lat * Math.PI / 180), M0 = 156543.03392 * cosLat;
    const STEPS = 512, zoomAt = new Uint8Array(STEPS + 1), distAt = new Float64Array(STEPS + 1);
    for (let i = 0; i <= STEPS; i++) {
      const u = i / STEPS;
      distAt[i] = f.c * (Math.exp(f.k * u) - 1);
      const perPixel = f.c * f.k * Math.exp(f.k * u) / half;          // metres per canvas pixel, along the radius
      zoomAt[i] = Math.max(2, Math.min(maxZoom, Math.ceil(Math.log2(M0 / perPixel))));
    }
    const world = (east, north, z) => {
      const lat = m.lat + (fn + north) / 111320, lon = m.lon + (fe + east) / (111320 * cosLat), n = 2 ** z * 256;
      return [(lon + 180) / 360 * n, (0.5 - Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / (2 * Math.PI)) * n, n / 256];
    };
    /* which tiles: walk rays out from the house */
    const need = new Map();
    for (let i = 0; i <= STEPS; i += 4) {
      for (let a = 0; a < 360; a += 4) {
        const d = distAt[i], z = zoomAt[i];
        const [X, Y, n] = world(d * Math.sin(a * Math.PI / 180), d * Math.cos(a * Math.PI / 180), z);
        const tx = ((Math.floor(X / 256) % n) + n) % n, ty = Math.floor(Y / 256);
        if (ty >= 0 && ty < n) need.set(`${z}/${tx}/${ty}`, [z, tx, ty]);
      }
    }
    const keys = [...need.keys()];
    const pending = [...need.values()].map(([z, x, y]) => this._tile(z, x, y, url, referrer));
    const loaded = preview ? keys.map((key) => TILE_DATA.get(`${stem}|${key}`) || null) : await Promise.all(pending);
    if (run !== this._fishRun) return;                                  // a newer render has started
    const tiles = new Map(keys.map((key, i) => [key, loaded[i]]));
    const note = this.shadowRoot.querySelector('.note');
    const got = loaded.filter(Boolean).length;
    if (preview && !got) return;
    note.hidden = got > 0;
    if (!got) { note.textContent = 'This map source does not let its tiles be redrawn, so the fisheye view cannot use it. Try the other map style, or the true-scale map.'; return; }
    cv.width = cv.height = S;
    const ctx = cv.getContext('2d'), img = ctx.createImageData(S, S), out = img.data;
    for (let py = 0; py < S; py++) {
      const dy = py + 0.5 - half;
      for (let px = 0; px < S; px++) {
        const dx = px + 0.5 - half, r = Math.hypot(dx, dy) / half;
        if (r > 1) continue;
        const i = Math.min(STEPS, Math.round(r * STEPS)), z = zoomAt[i], d = distAt[i] / (r * half || 1);
        const [X, Y, n] = world(dx * d, -dy * d, z);
        const tx = ((Math.floor(X / 256) % n) + n) % n, ty = Math.floor(Y / 256);
        const data = tiles.get(`${z}/${tx}/${ty}`);
        const o = (py * S + px) * 4;
        if (!data) { out[o] = out[o + 1] = out[o + 2] = 46; out[o + 3] = 255; continue; }
        const t = ((Math.floor(Y) & 255) * 256 + (Math.floor(X) & 255)) * 4;
        out[o] = data[t] * 0.8; out[o + 1] = data[t + 1] * 0.8; out[o + 2] = data[t + 2] * 0.8; out[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  _fishPlot(st) {
    const R = 98, f = this._fishGet(), mi = this._mi, hyper = this._c.radar === 'hyperbolic';
    const key = `${f.range}|${this._meta.lat}|${this._meta.lon}|${this._c.map_style}`;
    if (this._fishDrawn !== key) { this._fishDrawn = key; this._fishRender(); }
    const rad = Math.PI / 180;
    const P = (bearing, metres) => this._fishPoint(metres * Math.sin(bearing * rad), metres * Math.cos(bearing * rad));
    const metresAt = (units) => f.c * (Math.exp(f.k * Math.min(1, units / R)) - 1);   // what a radius means at the house
    const moved = Math.hypot(this._focus.e, this._focus.n) > 1;
    let s = `<svg viewBox="-100 -100 200 200" role="img" aria-label="Where sounds are coming from, on a ${hyper ? 'hyperbolic' : 'fisheye'} map">`;
    s += `<circle class="rim" r="${R}"/>`;
    const marks = mi ? [[60.96, '200 ft'], [402.3, '¼ mi'], [1609.3, '1 mi'], [4828, '3 mi'], [16093, '10 mi'], [48280, '30 mi']]
      : [[50, '50 m'], [250, '250 m'], [1000, '1 km'], [3000, '3 km'], [10000, '10 km'], [30000, '30 km']];
    for (const [d, label] of marks) {
      const u = this._fishU(d);
      if (u < 0.14 || u > 0.93) continue;
      s += `<circle class="ring" r="${(R * u).toFixed(1)}"/><text class="rl" x="2" y="${(-R * u + 6).toFixed(1)}">${label}</text>`;
    }
    s += `<text class="rl" x="2" y="${-R + 6}">${this._dist(f.range / 1000)}</text>`;
    const far = Math.max(1, ...st.mics.map((m) => m.distance));
    const rIcon = Math.min(60, Math.max(22, R * this._fishU(far + 15)));
    /* Sounds are placed by bearing from the house; once the focus has moved, each point goes through the lens. */
    s += this._sounds(st, rIcon + 16, rIcon, moved ? (b, units) => P(b, metresAt(units)).slice(0, 2) : undefined);
    const [hx, hy] = this._fishPoint(0, 0);
    s += `<circle class="home" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="2.4"/>`;
    s += this._mics(st, (m) => {
      const [x, y] = P(m.bearing, m.distance), len = Math.hypot(x - hx, y - hy) || 1;
      return [x, y, x + (x - hx) / len * 6, y + (y - hy) / len * 6];
    });
    if (moved) s += '<path class="cross" d="M-4 0 H4 M0 -4 V4"/>';
    const hot = this._hot(st);
    for (const a of this._planes(st, hot)) {
      const on = hot.has(a.hex);
      let [x, y, u] = P(on ? a.heard_bearing : a.bearing, (on ? a.heard_km : a.km) * 1000);
      if (u > 1.08 && !on && a.audible < 0.25) continue;
      if (u > 0.93) { x *= 0.93 / Math.min(u, 1); y *= 0.93 / Math.min(u, 1); }
      s += this._plane(a, x, y, on, u > 0.93 ? 'far' : on || a.audible >= 0.25);
    }
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

  /* ------------------------------------------- the recording of one sound */
  _clipUi(open) {
    const root = this.shadowRoot, el = root.querySelector('.clip');
    if (!el) return;
    if (!open) { el.hidden = true; if (this._clipId != null) { this._clipStop(); this._clipId = null; this._clip = null; } return; }
    el.hidden = false;
    if (this._clipId !== open.id) {
      this._clipStop();
      this._clipId = open.id; this._clip = null; this._clipFailed = false; this._iso = false;
    }
    if (open.clip && !this._clip && !this._clipBusy && !this._clipFailed) this._clipLoad(open);
    const have = this._clip?.id === open.id;
    const mic = have ? this._state.mics.find((m) => m.id === this._clip.mic)?.name || this._clip.mic : '';
    const infoText = have ? `${mic} · ${Math.round(this._clip.seconds)} s${this._iso ? ` · ${this._clip.band[0]}–${this._clip.band[1]} Hz, background removed` : ' · as recorded'}`
      : this._clipFailed ? 'The recording could not be loaded.'
        : open.clip ? 'Loading the recording…'
          : open.active ? 'A recording will be ready a few seconds after this ends.' : 'No recording was kept for this sound.';
    // Each part stays whole; a long line breaks after a bullet instead of being cut off.
    const info = root.querySelector('.cinfo'), parts = infoText.split(' · ');
    info.title = infoText;
    info.replaceChildren(...parts.flatMap((p, k) => {
      const span = document.createElement('span');
      span.textContent = k < parts.length - 1 ? `${p} ·` : p;
      return k ? [' ', span] : [span];
    }));
    root.querySelector('.cframe').hidden = !have;
    // Words, for voices only, and only when asked for.
    const said = this._said = this._said || {}, tr = said[open.id] || (open.extra?.transcript != null ? { text: open.extra.transcript, engine: open.extra.transcribed_by } : null);
    const tb = root.querySelector('.ctext'), tx = root.querySelector('.ctrans');
    tb.hidden = open.cls !== 'voice' || !!(tr && !tr.error && !tr.busy);
    tb.disabled = !open.clip || !!tr?.busy;
    tx.hidden = open.cls !== 'voice' || !tr;
    if (tr) {
      tx.classList.toggle('err', !!tr.error);
      tx.textContent = tr.busy ? 'Transcribing…' : tr.error ? tr.error : tr.text ? `“${tr.text}”` : 'No words could be made out.';
      tx.title = tr.engine ? `Transcribed by ${tr.engine}` : '';
    }
    for (const b of root.querySelectorAll('.cplay, .ciso')) b.disabled = !have;
    root.querySelector('.ciso').classList.toggle('on', !!this._iso);
    root.querySelector('.cplay').firstElementChild.setAttribute('icon', this._play ? 'mdi:stop' : 'mdi:play');
    if (have) {
      const c = this._clip, at = (t) => Math.max(0, Math.min(100, (t - c.t0) / c.seconds * 100));
      this._set('.cmarks', `<span style="left:${at(open.start).toFixed(1)}%">reported</span>${open.end ? `<i style="left:${at(open.end).toFixed(1)}%"></i>` : ''}`);
    }
  }

  async _transcribe(id) {
    if (id == null) return;
    const said = this._said = this._said || {};
    said[id] = { busy: true };
    this._render();
    try {
      const r = await this._hass.callWS({ type: 'soundscape/transcribe', event: id });
      said[id] = { text: r.text, engine: r.engine };
    } catch (err) {
      said[id] = { error: err?.code === 'no_engine'
        ? 'No speech-to-text engine is set up. Add one under Settings → Voice assistants (Whisper, for example).'
        : err?.message || 'The recording could not be transcribed.' };
    }
    this._render();
  }

  async _clipLoad(ev) {
    this._clipBusy = true;
    try {
      const r = await this._hass.callWS({ type: 'soundscape/clip', event: ev.id });
      const bytes = b64(r.data), n = bytes.length >> 1, pcm = new Int16Array(bytes.buffer, 0, n), x = new Float32Array(n);
      for (let i = 0; i < n; i++) x[i] = pcm[i] / 32768;
      if (this._clipId !== ev.id) return;
      this._clip = { id: ev.id, x, rate: r.rate, t0: r.t0, mic: r.mic, seconds: n / r.rate, band: ISOLATE[ev.cls] || [60, 11000], ...this._clipSpectra(x, r.rate, ISOLATE[ev.cls] || [60, 11000]) };
      this._clipDraw();
    } catch (err) {
      if (this._clipId === ev.id) this._clipFailed = true;
    } finally {
      this._clipBusy = false;
      if (this._state) this._render();
    }
  }

  /* Two pictures of the recording on the card's usual frequency scale: as recorded, and isolated. */
  _clipSpectra(x, rate, band) {
    const N = 1024, HOP = 256, GROUP = 4, half = N / 2 + 1, bands = this._meta.bands, edges = this._meta.edges;
    const frames = Math.max(0, Math.floor((x.length - N) / HOP) + 1), cols = Math.floor(frames / GROUP);
    if (!cols) return { cols: 0 };
    const fft = SoundscapeCard._fft || (SoundscapeCard._fft = makeFFT(N));
    const win = new Float32Array(N); for (let i = 0; i < N; i++) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
    const re = new Float32Array(N), im = new Float32Array(N), P = new Float32Array(cols * half);
    for (let c = 0; c < cols; c++) {
      for (let g = 0; g < GROUP; g++) {
        const o = (c * GROUP + g) * HOP;
        for (let i = 0; i < N; i++) re[i] = x[o + i] * win[i];
        fft(re, im);
        for (let k = 0; k < half; k++) P[c * half + k] += (re[k] * re[k] + im[k] * im[k]) / GROUP;
      }
    }
    /* each bin's steady background: its quiet level over the recording */
    const floor = new Float32Array(half), col = new Float32Array(cols);
    for (let k = 0; k < half; k++) {
      for (let c = 0; c < cols; c++) col[c] = P[c * half + k];
      floor[k] = Array.from(col).sort((a, b) => a - b)[Math.floor(cols * 0.2)] + 1e-12;
    }
    const lo = new Uint16Array(bands), hi = new Uint16Array(bands), hz = rate / N;
    for (let b = 0; b < bands; b++) { lo[b] = Math.min(half - 1, Math.floor(edges[b] / hz)); hi[b] = Math.min(half, Math.max(lo[b] + 1, Math.ceil(edges[b + 1] / hz))); }
    const k0 = Math.floor(band[0] / hz), k1 = Math.ceil(band[1] / hz);
    const db = new Float32Array(cols * bands), iso = new Uint8Array(cols * bands);
    for (let c = 0; c < cols; c++) {
      for (let b = 0; b < bands; b++) {
        let sum = 0, extra = 0, base = 0;
        for (let k = lo[b]; k < hi[b]; k++) {
          const p = P[c * half + k];
          sum += p; base += floor[k];
          if (k >= k0 && k <= k1) extra += Math.max(0, p - 4 * floor[k]);     // only what clearly stands above the background
        }
        db[c * bands + b] = 10 * Math.log10(sum / (hi[b] - lo[b]) + 1e-14);
        iso[c * bands + b] = Math.max(0, Math.min(255, 10 * Math.log10(1 + extra / base) / 34 * 255));
      }
    }
    /* as recorded: stretch the colours between the quiet and loud ends, as the live view does */
    const sorted = Array.from(db).sort((a, b) => a - b), a = sorted[Math.floor(sorted.length * 0.08)] - 2;
    const z = Math.max(sorted[Math.floor(sorted.length * 0.997)] + 3, a + 35), raw = new Uint8Array(cols * bands);
    for (let i = 0; i < db.length; i++) raw[i] = Math.max(0, Math.min(255, (db[i] - a) / (z - a) * 255));
    return { cols, raw, iso };
  }

  _clipDraw() {
    const cv = this.shadowRoot.querySelector('.cspec'), c = this._clip;
    if (!cv || !c?.cols) return;
    const bands = this._meta.bands, src = this._iso ? c.iso : c.raw;
    cv.width = c.cols; cv.height = bands;
    const ctx = cv.getContext('2d'), img = ctx.createImageData(c.cols, bands);
    for (let x = 0; x < c.cols; x++) {
      for (let b = 0; b < bands; b++) {
        const v = src[x * bands + b] * 4, o = ((bands - 1 - b) * c.cols + x) * 4;
        img.data[o] = LUT[v]; img.data[o + 1] = LUT[v + 1]; img.data[o + 2] = LUT[v + 2]; img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  _clipIsolate(on) {
    this._iso = on;
    this._clipDraw();
    if (this._play) this._clipPlay(this._clipPos());      // carry on from the same place, through the filter or not
    else if (this._state) this._render();
  }

  _clipPos() { return this._play ? this._clipCtx.currentTime - this._play.since : 0; }

  /* Plays the recording untouched; with Isolate on, through a band-pass for that kind of sound. */
  _clipPlay(from) {
    const c = this._clip;
    if (!c) return;
    this._clipStop();
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this._clipCtx = this._clipCtx || new Ctx();
    const ctx = this._clipCtx;
    ctx.resume?.();
    const buf = ctx.createBuffer(1, c.x.length, c.rate);
    buf.getChannelData(0).set(c.x);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    let node = src;
    if (this._iso) {
      for (const [type, f] of [['highpass', c.band[0]], ['highpass', c.band[0]], ['lowpass', c.band[1]], ['lowpass', c.band[1]]]) {
        const q = ctx.createBiquadFilter();
        q.type = type; q.frequency.value = Math.min(f, c.rate / 2 * 0.95); q.Q.value = 0.707;
        node.connect(q); node = q;
      }
    }
    const gain = ctx.createGain();
    gain.gain.value = this._volume ** 2 * 4;
    this._clipGain = gain;
    node.connect(gain); gain.connect(ctx.destination);
    const offset = Math.max(0, Math.min(c.seconds - 0.05, from || 0));
    const play = this._play = { src, since: ctx.currentTime - offset };
    src.onended = () => { if (this._play === play) this._clipStop(); };
    src.start(0, offset);
    const cursor = this.shadowRoot.querySelector('.ccursor');
    const tick = () => {
      if (this._play !== play) return;
      cursor.hidden = false;
      cursor.style.left = `${Math.min(100, this._clipPos() / c.seconds * 100)}%`;
      requestAnimationFrame(tick);
    };
    tick();
    if (this._state) this._render();
  }

  _clipStop() {
    const play = this._play;
    this._play = null;
    if (play) { try { play.src.onended = null; play.src.stop(); } catch (e) { /* already stopped */ } }
    const cursor = this.shadowRoot?.querySelector('.ccursor');
    if (cursor) cursor.hidden = true;
    if (play && this._state && this._built) this._render();
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
    if (this._clipGain) this._clipGain.gain.value = this._volume ** 2 * 4;
    root?.querySelector('.cvolicon')?.setAttribute('icon', this._volume ? 'mdi:volume-high' : 'mdi:volume-off');
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
  ha-card { overflow: hidden; position: relative; }
  .body { padding: 0 16px 16px; }
  /* A plain 20 px medium title. Each part can be restyled from a theme or card-mod with the variables. */
  .head { display: flex; align-items: baseline; gap: 12px; padding: var(--soundscape-title-padding, 14px 16px 6px); }
  .title { flex: 1; font-size: var(--soundscape-title-font-size, 20px); font-weight: var(--soundscape-title-font-weight, 500);
    line-height: var(--soundscape-title-line-height, 28px); color: var(--soundscape-title-color, var(--primary-text-color)); }
  .ticon { align-self: center; flex: none; margin-right: -4px; color: var(--soundscape-title-icon-color, var(--secondary-text-color)); --mdc-icon-size: 22px; }
  .status { font-size: 12px; color: var(--secondary-text-color); }
  .body { padding-top: 6px; }
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
  .fb { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 8px; }
  .fbq { color: var(--secondary-text-color); margin-right: 2px; }
  .fb button, .fb select { all: unset; cursor: pointer; height: 26px; padding: 0 9px; box-sizing: border-box; display: inline-flex; align-items: center; gap: 4px;
    border-radius: 13px; border: 1px solid var(--divider-color); color: var(--primary-text-color); font-size: 12px; --mdc-icon-size: 16px; }
  .fb select { padding-right: 22px; background: no-repeat right 8px center / 8px url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E"); }
  .fb select option { color: initial; background: initial; }
  .fb .on { background: var(--success-color, #43a047); border-color: var(--success-color, #43a047); color: #fff; }
  .fb .on.bad, .fb select.on { background: var(--error-color, #db4437); border-color: var(--error-color, #db4437); color: #fff; }
  .fbnote { margin-top: 6px; color: var(--secondary-text-color); font-size: 12px; }
  .fbnote a { color: var(--primary-color); cursor: pointer; text-decoration: underline; }
  .why ul { margin: 4px 0 0; padding-left: 18px; color: var(--secondary-text-color); }
  .lv { display: grid; grid-template-columns: auto 1fr auto; gap: 3px 8px; align-items: center; margin-top: 6px; color: var(--secondary-text-color); }
  .lv i { height: 5px; border-radius: 3px; background: color-mix(in srgb, var(--primary-text-color) 12%, transparent); }
  .lv b { display: block; height: 100%; border-radius: 3px; background: var(--primary-color); }

  .clip { margin-top: 8px; }
  .cbar { display: flex; align-items: center; gap: 6px; }
  .cinfo > span { white-space: nowrap; }
  .cbar button { all: unset; cursor: pointer; height: 26px; min-width: 28px; padding: 0 8px; box-sizing: border-box; display: inline-flex; align-items: center; justify-content: center; gap: 4px;
    border-radius: 13px; border: 1px solid var(--divider-color); color: var(--primary-text-color); font-size: 12px; --mdc-icon-size: 16px; }
  .cbar button.on, .cbar .cplay { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .cbar button[disabled] { opacity: .4; pointer-events: none; }
  .cinfo { flex: 1 1 120px; min-width: 0; line-height: 1.35; font-size: 12px; color: var(--secondary-text-color); margin-left: 4px; }
  .ctrans { margin-top: 6px; padding: 6px 10px; border-radius: 8px; font-size: 13px; line-height: 1.35; color: var(--primary-text-color);
    background: var(--secondary-background-color, rgba(127,127,127,.12)); }
  .ctrans.err { color: var(--error-color, #db4437); }
  .ctrans[hidden], .cbar button[hidden] { display: none; }
  .cframe { position: relative; height: 110px; margin-top: 6px; border-radius: 8px; overflow: hidden; background: #000; cursor: pointer; }
  .cframe[hidden], .ccursor[hidden] { display: none; }
  .cspec { position: absolute; inset: 0; width: 100%; height: 100%; }
  .cmarks span, .cmarks i { position: absolute; top: 0; bottom: 0; border-left: 1px dashed rgba(255,255,255,.75); }
  .cmarks span { padding: 2px 4px; font-size: 10px; color: #fff; text-shadow: 0 0 3px #000; white-space: nowrap; }
  .ccursor { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: #fff; box-shadow: 0 0 3px #000; pointer-events: none; }

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

  .radar.map { aspect-ratio: 1; border-radius: 12px; overflow: hidden; background: #2a2d31; touch-action: none; cursor: grab; user-select: none; }
  .radar.map .tiles, .radar.map .plot { transform-origin: 50% 50%; }
  .mapctl { position: absolute; left: 8px; top: 8px; display: flex; flex-direction: column; gap: 4px; }
  .mapctl button { all: unset; cursor: pointer; width: 28px; height: 28px; display: grid; place-items: center; border-radius: 8px;
    background: rgba(255,255,255,.88); color: #222; font: 500 18px/1 sans-serif; box-shadow: 0 1px 3px rgba(0,0,0,.4); --mdc-icon-size: 18px; }
  .mapctl button[hidden] { display: none; }
  .mapctl .sethome { background: #1e88e5; color: #fff; }
  .cross { stroke: #fff; stroke-width: .8; fill: none; filter: drop-shadow(0 0 1px #000); }
  .radar.fish { background: none; border-radius: 0; overflow: visible; touch-action: auto; cursor: default; }
  .radar.hyper { touch-action: none; cursor: grab; } .radar.hyper.dragging { cursor: grabbing; }
  .radar.fish canvas.warp { position: absolute; inset: 1%; width: 98%; height: 98%; border-radius: 50%; background: #2a2d31; }
  .radar.fish .ring { stroke: rgba(255,255,255,.5); stroke-width: .5; }
  .radar.fish .rim { fill: none; stroke: var(--divider-color); stroke-width: .8; }
  .radar.fish .credit { border-radius: 6px; right: 4px; bottom: 4px; }
  .note { position: absolute; inset: 30% 12%; display: grid; place-items: center; text-align: center; font-size: 13px; color: #fff; }
  .note[hidden] { display: none; }
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
  .vol, .cvol { width: 84px; accent-color: var(--primary-color); }
  .cvolicon { --mdc-icon-size: 18px; color: var(--secondary-text-color); margin-left: 4px; }
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
