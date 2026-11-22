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
                route.fulfill(body=tile(sum(map(ord, route.request.url))), content_type="image/png")
            pg.route("**/tile.openstreetmap.org/**", serve)
            pg.route("**/server.arcgisonline.com/**", serve)
            pg.goto(f"http://127.0.0.1:8765/dev/harness.html?theme={theme}&config={quote(json.dumps(config))}" + (f"&open={opened}" if opened else ""))
            pg.wait_for_function("window.ready === true", timeout=15000)
            pg.wait_for_timeout(700)
            pg.screenshot(path=f"shot-{name}.png", full_page=True)
            print(name, "errors:", errs, "tiles:", len(tiles), tiles[:1])
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
        b.close()
finally:
    srv.terminate()
