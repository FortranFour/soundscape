"""Render the card from dev/fixture.json in headless Chrome and exercise its controls."""
import base64, json, struct, subprocess, sys, time, zlib
from urllib.parse import quote
from playwright.sync_api import sync_playwright


def tile(seed):
    """A stand-in map tile: muted colour by tile, with a border, so alignment shows."""
    w = 256
    r, g, b = 70 + seed * 37 % 60, 90 + seed * 53 % 50, 80 + seed * 29 % 50
    rows = b""
    for y in range(w):
        row = bytearray()
        for x in range(w):
            edge = x < 2 or y < 2 or (x // 32 + y // 32) % 2 == 0 and (x % 32 < 1 or y % 32 < 1)
            row += bytes((200, 200, 200) if edge else (r, g, b))
        rows += b"\x00" + bytes(row)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, w, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


SHOTS = {
    "light": ({}, "light", "siren"),
    "dark": ({}, "dark", None),
    "map": ({"radar": "map", "map_style": "satellite", "map_radius_m": 60, "log_rows": 5}, "dark", None),
    "fisheye": ({"radar": "fisheye", "map_style": "satellite", "range_mi": 6, "map_radius_ft": 200, "show_log": False, "show_spectrogram": False}, "dark", None),
    "fisheye-heard": ({"radar": "fisheye", "aircraft": "heard", "show_log": False, "show_spectrogram": False}, "light", None),
    "map-wide": ({"radar": "map", "map_radius_m": 3000, "units": "km", "show_log": False, "show_spectrogram": False}, "light", None),
}
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765", "--bind", "127.0.0.1"], cwd="..",
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        for name, (config, theme, opened) in SHOTS.items():
            pg = b.new_page(viewport={"width": 520, "height": 900}, device_scale_factor=2)
            errs, tiles = [], []
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "favicon" not in m.text and "404" not in m.text else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))

            def serve(route):
                tiles.append(route.request.url)
                route.fulfill(body=tile(sum(map(ord, route.request.url))), content_type="image/png",
                              headers={"Access-Control-Allow-Origin": "*"})
            pg.route("**/api/map_tiles/raster/**", serve)
            pg.route("**/tile.openstreetmap.org/**", serve)
            pg.route("**/server.arcgisonline.com/**", serve)
            pg.goto(f"http://127.0.0.1:8765/dev/harness.html?theme={theme}&config={quote(json.dumps(config))}" + (f"&open={opened}" if opened else ""))
            pg.wait_for_function("window.ready === true", timeout=15000)
            pg.wait_for_timeout(1800 if "fisheye" in name else 700)
            pg.screenshot(path=f"shot-{name}.png", full_page=True)
            print(name, "errors:", errs, "tiles:", len(tiles), tiles[:1])
            if "fisheye" in name:
                print("  ", pg.evaluate("""(() => { const cv = card.shadowRoot.querySelector('canvas.warp'), d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
                    let lit = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] && (d[i] !== 46 || d[i + 1] !== 46)) lit++;
                    return {size: cv.width, covered: Math.round(lit / (Math.PI * cv.width * cv.width / 4) * 100) + '%',
                            zooms: [...new Set([...card.shadowRoot.host.constructor ? [] : []])].length,
                            planes: card.shadowRoot.querySelectorAll('.plot .ac').length, note: !card.shadowRoot.querySelector('.note').hidden}; })()"""),
                      "zoom levels:", sorted({int(u.split("/tile/")[1].split("/")[0]) if "/tile/" in u else int(u.split("/raster/")[1].split("/")[0]) for u in tiles}))
            if name == "dark":
                # scrolling list keeps its place across updates; filters; live audio controls
                rows = pg.evaluate("card.shadowRoot.querySelectorAll('.log .row').length")
                pg.evaluate("card.shadowRoot.querySelector('.log').scrollTop = 120")
                pg.evaluate("window.feed({...card._state, type: 'state', now: card._state.now + 1})")
                kept = pg.evaluate("card.shadowRoot.querySelector('.log').scrollTop")
                pg.evaluate("card.shadowRoot.querySelector('[data-filter=air]').click()")
                air = pg.evaluate("card.shadowRoot.querySelectorAll('.log .row').length")
                pg.evaluate("card.shadowRoot.querySelector('.hear').click()")
                pg.wait_for_timeout(100)
                pcm = base64.b64encode(struct.pack("<8000h", *([0, 3000, 0, -3000] * 2000))).decode()
                pg.evaluate("d => { for (let i = 0; i < 4; i++) window.pcm({type: 'pcm', mic: card._listening, rate: 24000, data: d}); }", pcm)
                state = pg.evaluate("({l: card._listening, vol: !card.shadowRoot.querySelector('.vol').hidden, queued: card._playAt - card._audio.currentTime, gain: card._gain.gain.value})")
                pg.evaluate("card.shadowRoot.querySelector('.mute').click()")
                muted = pg.evaluate("card._gain.gain.value")
                pg.evaluate("card.shadowRoot.querySelector('[data-mic=Backyard]').click()")
                pg.wait_for_timeout(100)
                pg.evaluate("card.shadowRoot.querySelector('.hear').click()")
                print("rows", rows, "scroll kept", kept, "aircraft rows", air, "listen", state, "muted gain", muted,
                      "calls", pg.evaluate("window.calls"), "errors", errs)
        # ---- map: zoom buttons, wheel, drag, and "the house is here"
        pg = b.new_page(viewport={"width": 520, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/api/map_tiles/raster/**", lambda r: r.fulfill(body=tile(3), content_type="image/png"))
        pg.goto("http://127.0.0.1:8765/dev/harness.html?theme=dark&config=" + quote(json.dumps({"radar": "map", "map_radius_ft": 200})))
        pg.wait_for_function("window.ready === true", timeout=15000)
        view = lambda: pg.evaluate("({r: Math.round(card._view.radius * 10) / 10, ox: Math.round(card._view.ox), oy: Math.round(card._view.oy), pin: !card.shadowRoot.querySelector('.sethome').hidden, ref: card.shadowRoot.querySelector('.tiles img').hasAttribute('referrerpolicy')})")  # noqa: E731
        print("map start", view())
        pg.evaluate("card.shadowRoot.querySelector('[data-zoom=\"1.6\"]').click()")
        print("zoomed out", view())
        box = pg.evaluate("(() => { const r = card.shadowRoot.querySelector('.radar').getBoundingClientRect(); return [r.x, r.y, r.width]; })()")
        cx, cy = box[0] + box[2] / 2, box[1] + box[2] / 2
        pg.mouse.move(cx, cy); pg.mouse.wheel(0, -200); pg.wait_for_timeout(200)
        print("wheel in", view())
        pg.mouse.move(cx, cy); pg.mouse.down(); pg.mouse.move(cx + 40, cy, steps=4); pg.mouse.move(cx + box[2] / 4, cy - box[2] / 8, steps=4); pg.mouse.up()
        pg.wait_for_timeout(350)
        v = view(); print("dragged", v, "(map moved right and up: the middle is now west and south of the house)")
        pg.screenshot(path="shot-map-moved.png", full_page=True)
        pg.evaluate("card.shadowRoot.querySelector('.sethome').click()"); pg.wait_for_timeout(100)
        print("saved", [c for c in pg.evaluate("window.calls") if "set_home" in c])
        pg.evaluate("window.feed({type: 'meta', meta: {...card._meta, lat: card._meta.lat - 0.0001}})")
        print("after house moved", view())
        pg.reload(); pg.wait_for_function("window.ready === true", timeout=15000)
        print("after reload (zoom remembered)", view(), "errors", errs)
        # ---- a past sound's recording: its spectrogram as recorded and isolated, play, seek
        pg = b.new_page(viewport={"width": 520, "height": 620}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8765/dev/harness.html?theme=dark&recent=siren&config=" + quote(json.dumps({"show_radar": False, "show_spectrogram": False, "log_rows": 4})))
        pg.wait_for_function("window.ready === true", timeout=15000)
        pg.wait_for_function("card._clip && card._clip.cols > 0", timeout=15000)
        info = lambda: pg.evaluate("card.shadowRoot.querySelector('.cinfo').textContent")  # noqa: E731
        lit = lambda: pg.evaluate("(() => { const c = card.shadowRoot.querySelector('.cspec'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] > 90) n++; return Math.round(n / (c.width * c.height) * 100); })()")  # noqa: E731
        print("clip:", info(), "| columns", pg.evaluate("card._clip.cols"), "| bright", lit(), "%")
        pg.screenshot(path="shot-clip.png", full_page=True)
        pg.evaluate("card.shadowRoot.querySelector('.ciso').click()"); pg.wait_for_timeout(200)
        print("isolated:", info(), "| bright", lit(), "%")
        pg.screenshot(path="shot-clip-isolated.png", full_page=True)
        for w in (520, 380):
            pg.set_viewport_size({"width": w, "height": 620}); pg.wait_for_timeout(150)
            print(f"isolated at {w}px: info lines", pg.evaluate("(() => { const e = card.shadowRoot.querySelector('.cinfo'); return Math.round(e.getBoundingClientRect().height / 16); })()"),
                  "| cut off:", pg.evaluate("(() => { const e = card.shadowRoot.querySelector('.cinfo'); return e.scrollWidth > e.clientWidth + 1; })()"))
            pg.screenshot(path=f"shot-clip-isolated-{w}.png", full_page=True)
        pg.set_viewport_size({"width": 520, "height": 620})
        pg.evaluate("card.shadowRoot.querySelector('.cplay').click()"); pg.wait_for_timeout(700)
        p1 = pg.evaluate("card._clipPos()")
        box = pg.evaluate("(() => { const r = card.shadowRoot.querySelector('.cframe').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        pg.mouse.click(box[0] + box[2] * 0.5, box[1] + box[3] / 2); pg.wait_for_timeout(300)
        p2 = pg.evaluate("card._clipPos()")
        pg.evaluate("card.shadowRoot.querySelector('.cplay').click()"); pg.wait_for_timeout(100)
        print("playing at", round(p1, 2), "s; after a click halfway", round(p2, 2), "s; stopped:", pg.evaluate("card._play === null"), "| errors", errs)

        # ---- a voice: words on request
        for stt in ("1", "0"):
            pg = b.new_page(viewport={"width": 520, "height": 620}, device_scale_factor=2)
            pg.goto("http://127.0.0.1:8765/dev/harness.html?theme=dark&recent=voice&stt=" + stt + "&config=" + quote(json.dumps({"show_radar": False, "show_spectrogram": False, "log_rows": 4})))
            pg.wait_for_function("window.ready === true", timeout=15000)
            pg.wait_for_function("card._clip && card._clip.cols > 0", timeout=15000)
            q = lambda sel, what: pg.evaluate(f"(() => {{ const e = card.shadowRoot.querySelector('{sel}'); return e.{what}; }})()")  # noqa: E731
            before = (q(".ctext", "hidden"), q(".ctrans", "hidden"))
            pg.evaluate("card.shadowRoot.querySelector('.ctext').click()"); pg.wait_for_timeout(100)
            during = q(".ctrans", "textContent")
            pg.wait_for_timeout(600)
            print("voice, engine" if stt == "1" else "voice, no engine", "| button hidden, text hidden before:", before, "| during:", during,
                  "| after:", q(".ctrans", "textContent"), "| button hidden after:", q(".ctext", "hidden"))
            if stt == "1":
                pg.screenshot(path="shot-voice.png", full_page=True)

        # ---- feedback on a past sound
        pg = b.new_page(viewport={"width": 520, "height": 700}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8765/dev/harness.html?theme=dark&recent=vehicle&config=" + quote(json.dumps({"show_radar": False, "show_spectrogram": False, "log_rows": 4})))
        pg.wait_for_function("window.ready === true", timeout=15000)
        pg.evaluate("card.shadowRoot.querySelector('[data-fb=wrong]').click()"); pg.wait_for_timeout(300)
        note = pg.evaluate("card.shadowRoot.querySelector('.fbnote')?.textContent || ''")
        on = pg.evaluate("card.shadowRoot.querySelector('[data-fb=wrong]').classList.contains('on')")
        pg.screenshot(path="shot-feedback.png", full_page=True)
        pg.select_option("select.fbwas", "weather"); pg.wait_for_timeout(300)
        sent = pg.evaluate("window.answers")
        pg.evaluate("card.shadowRoot.querySelector('[data-fb=right]').click()"); pg.wait_for_timeout(300)
        print("feedback: wrong lit", on, "| note:", note.strip()[:90], "| sent:", [(a["verdict"], a.get("actual")) for a in sent],
              "| then right:", pg.evaluate("window.answers.at(-1).verdict"), "| errors", errs)

        # ---- hyperbolic: drag a place to the middle and it stays under the pointer
        pg = b.new_page(viewport={"width": 520, "height": 760}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/server.arcgisonline.com/**", lambda r: r.fulfill(body=tile(sum(map(ord, r.request.url))), content_type="image/png", headers={"Access-Control-Allow-Origin": "*"}))
        pg.goto("http://127.0.0.1:8765/dev/harness.html?theme=dark&config=" + quote(json.dumps({"radar": "hyperbolic", "map_style": "satellite", "range_mi": 6, "map_radius_ft": 200, "show_log": False, "show_spectrogram": False})))
        pg.wait_for_function("window.ready === true", timeout=15000); pg.wait_for_timeout(1500)
        box = pg.evaluate("(() => { const r = card.shadowRoot.querySelector('.radar').getBoundingClientRect(); return [r.x, r.y, r.width]; })()")
        cx, cy, w = box[0] + box[2] / 2, box[1] + box[2] / 2, box[2]
        sx, sy = cx + w * 0.30, cy - w * 0.22                      # a spot up and to the right, a few miles out
        under = lambda x, y: pg.evaluate("([x, y]) => { const g = card._fishGround(x, y); return [Math.round(card._focus.e + g[0]), Math.round(card._focus.n + g[1])]; }", [(x - cx) / w * 200, (y - cy) / w * 200])  # noqa: E731
        before = under(sx, sy)
        pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.move(cx + w * 0.15, cy - w * 0.1, steps=5); pg.mouse.move(cx, cy, steps=5)
        pg.wait_for_timeout(150)
        mid = pg.evaluate("card.shadowRoot.querySelector('canvas.warp').width")
        pg.mouse.up(); pg.wait_for_timeout(1500)
        after = under(cx, cy)
        print("hyperbolic: grabbed ground point", before, "-> now under the middle", after, "| focus", pg.evaluate("[Math.round(card._focus.e), Math.round(card._focus.n)]"),
              "| canvas while dragging", mid, "after", pg.evaluate("card.shadowRoot.querySelector('canvas.warp').width"), "| errors", errs)
        pg.screenshot(path="shot-hyperbolic.png", full_page=True)
        pg.wait_for_timeout(300); pg.evaluate("card.shadowRoot.querySelector('.recenter').click()"); pg.wait_for_timeout(600)
        print("home button -> focus", pg.evaluate("[card._focus.e, card._focus.n]"), "errors", errs)

        # ---- streets on a Home Assistant without the tile proxy: straight from OpenStreetMap, saying where from
        pg = b.new_page(viewport={"width": 520, "height": 700})
        seen = []
        pg.route("**/tile.openstreetmap.org/**", lambda r: (seen.append(r.request.headers.get("referer")), r.fulfill(body=tile(3), content_type="image/png")))
        pg.goto("http://127.0.0.1:8765/dev/harness.html?proxy=0&theme=dark&config=" + quote(json.dumps({"radar": "map"})))
        pg.wait_for_function("window.ready === true", timeout=15000); pg.wait_for_timeout(800)
        print("no proxy -> OpenStreetMap tiles:", len(seen), "referer sent:", set(seen),
              "| policy on img:", pg.evaluate("card.shadowRoot.querySelector('.tiles img')?.getAttribute('referrerpolicy')"))
        # ---- the frame is permanent: a style node put into the shadow root at creation survives everything
        pg.evaluate("""(() => { const c = document.createElement('soundscape-card'); c.setConfig({title: 'X', card_mod: {style: 'x'}});
            const before = !!c.shadowRoot?.querySelector('ha-card'); const mark = document.createElement('uix-node'); c.shadowRoot.appendChild(mark);
            const frame = c.shadowRoot.querySelector('ha-card'); document.body.append(c); c.hass = card._hass; window.probe = {c, before, frame}; })()""")
        pg.wait_for_timeout(500)
        print("frame before attach:", pg.evaluate("probe.before"), "| style node kept:", pg.evaluate("!!probe.c.shadowRoot.querySelector('uix-node')"),
              "| same ha-card:", pg.evaluate("probe.frame === probe.c.shadowRoot.querySelector('ha-card')"), "| config visible:", pg.evaluate("!!probe.c._config.card_mod"),
              "| rendered:", pg.evaluate("!!probe.c.shadowRoot.querySelector('.now')"))

        # ---- fisheye when no tile can be read
        pg = b.new_page(viewport={"width": 520, "height": 700})
        pg.route("**/api/map_tiles/raster/**", lambda r: r.abort())
        pg.goto("http://127.0.0.1:8765/dev/harness.html?theme=dark&config=" + quote(json.dumps({"radar": "fisheye"})))
        pg.wait_for_function("window.ready === true", timeout=15000); pg.wait_for_timeout(1500)
        print("tiles unreadable -> note:", pg.evaluate("card.shadowRoot.querySelector('.note').textContent.slice(0, 60)"))
        b.close()
finally:
    srv.terminate()
