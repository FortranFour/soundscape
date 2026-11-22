"""Export brand/icon.svg and the wordmarks to the PNGs Home Assistant reads from the integration's brand folder."""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parents[1]
SRC, OUT = ROOT / "brand", ROOT / "custom_components/soundscape/brand"
icon = (SRC / "icon.svg").read_text()
mark = icon.replace('width="256" height="256"', 'x="16" y="16" width="128" height="128"')
for name, colour in (("logo", "#243445"), ("logo-dark", "#ffffff")):
    (SRC / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="160" viewBox="0 0 640 160">{mark}'
        f'<g fill="{colour}" font-family="Arial, sans-serif"><text x="168" y="96" font-size="48" font-weight="600">Soundscape</text></g></svg>\n')
TARGETS = {"icon": ("icon", "dark_icon"), "logo": ("logo",), "logo-dark": ("dark_logo",)}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for src, names in TARGETS.items():
        for scale in (1, 2):
            pg = b.new_page(device_scale_factor=scale, viewport={"width": 700, "height": 300})
            pg.set_content('<!doctype html><meta charset="utf-8"><style>body{margin:0;background:transparent}svg{display:block}</style>' + (SRC / f"{src}.svg").read_text())
            data = pg.locator("body > svg").screenshot(omit_background=True)
            for n in names:
                (OUT / f"{n}{'@2x' if scale == 2 else ''}.png").write_bytes(data)
            pg.close()
    b.close()
print(sorted(f.name for f in OUT.iterdir()))
