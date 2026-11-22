import subprocess, sys, time
from playwright.sync_api import sync_playwright
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765", "--bind", "127.0.0.1"], cwd="..", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for name, query in (("light", "?theme=light&open=siren"), ("dark", "?theme=dark")):
            pg = b.new_page(viewport={"width": 520, "height": 900}, device_scale_factor=2)
            errs = []
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://127.0.0.1:8765/dev/harness.html" + query)
            pg.wait_for_function("window.ready === true", timeout=15000)
            pg.wait_for_timeout(600)
            pg.screenshot(path=f"shot-{name}.png", full_page=True)
            print(name, "errors:", errs)
        b.close()
finally:
    srv.terminate()
