# Changelog

## 0.2.3

- Title is a plain 20 px medium heading, the size commonly used for card titles built with button-card, instead of the larger stock header. Its size, weight, line height, colour and padding can be set with `--soundscape-title-*` variables.
- card-mod and UIX styles on the card now apply; the card was keeping its configuration where they could not find it.
- Validation: the names of the aircraft sources are no longer translation keys, which may not contain a dot.

## 0.2.2

- Street maps now come from CARTO, as Home Assistant's own map does. OpenStreetMap's servers refuse requests without a page address, and Home Assistant stops the browser from sending one, so they could never have loaded.
- Setup help text no longer contains web addresses, which Home Assistant's validation rejects, and the manifest no longer names Frigate as a load-order dependency it does not need. No change in behaviour.

## 0.2.1

- Fisheye map: a third radar background that keeps the house near true scale and compresses distance logarithmically toward the rim, over real imagery.
- `aircraft` option: draw all nearby aircraft (as before), only those close enough to hear, or only those heard.
- Setup asks for the aircraft search radius in miles where Home Assistant uses miles.
- The map can be dragged and zoomed from the card, and the house can be put in the right place from the map (the blue pin).
- Street map tiles load again. They were refused because the card withheld the page address that OpenStreetMap's servers require.
- The editor shows the map reach and aircraft range in feet and miles where Home Assistant uses them, and lists every option's default. New cards get all options written out.
- The title uses Home Assistant's standard card header, so it follows the theme like other cards.
- On a zoomed-out map, a sound's icon stays by the house instead of sitting a fixed distance across the map.
- The spectrogram's colour range adapts to each microphone's level instead of saturating on loud cameras.
- A workflow checks the manifest, HACS requirements and the tests on every push and once a week.

## 0.2.0

- Map mode for the radar: a street or satellite map behind it at true scale, alongside the schematic logarithmic view, which stays the default.
- Icons on the radar: aircraft drawn by kind (jet, propeller, helicopter, Osprey) along their track; each ground sound with its icon and name; sounds that have ended stay on, faded, for two minutes.
- Listen live: a headphones button plays the shown microphone, with mute and volume.
- Recent sounds: the list scrolls, holds up to 150 entries, can leave kinds out, and has filter chips.
- Dispatch lists for twelve agencies in place of San Diego alone, with the nearest chosen automatically.
- Distances in miles and feet or kilometres and metres following Home Assistant's unit system, with an override in the integration and in the card. Microphone distances in setup follow the same units.
- Fixed the "formatjs" error shown under the audio address pattern and the ADS-B address in setup.
- The example coordinates in the tests and demo are now a public park.

## 0.1.0

- First build.
