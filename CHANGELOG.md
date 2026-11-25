# Changelog

## 0.7.1

- Stopping Soundscape now waits for each ffmpeg process and its error reader to finish. On a slow machine the reader could outlive the stop, which is what failed the GitHub test run.
- Workflow actions updated to versions that run on Node.js 24, and the duplicate dark icon removed, clearing the validation warnings.
- The test that runs Soundscape inside Home Assistant allows more time on a slow machine.

## 0.7.0

- Feedback that calibrates. Select a sound and answer **Right**, **Wrong**, or **It was…** (what it really was). Each answer counts for that kind of sound at that microphone only: every "wrong" lowers its confidence by 15 %, every "right" raises it by 5 %, within 40 % to 115 % of normal. "It was…" also counts as right for what it really was. Press an answer again to take it back.
- The selected sound shows how your answers have adjusted that kind of sound at that microphone, with a Reset link for administrators. The adjustments are kept across restarts and listed in the integration's diagnostics.
- A sound you answer for is saved with your answer in `media/soundscape` (the recording plus a line in `labels.jsonl`), up to 150 recordings, so detection can be tuned against your own yard. Voices are never saved: only the answer.
- A setting on the Microphones page, "Learn from answers" (on by default), switches this off: the buttons are hidden and every sound is judged as if no answers had been given. Answers already given are kept and count again when it is switched back on.

## 0.6.1

- The line beside a recording's controls (microphone, length, frequency band) wraps after a bullet instead of being cut off.

## 0.6.0

- Transcription. Select a voice in the list and press Transcribe beside Play: the recording goes to one of Home Assistant's speech-to-text engines (Whisper, Home Assistant Cloud, or any other you have) and the words appear under the buttons. Nothing is transcribed until you ask, and the words are kept with the sound until Home Assistant restarts.
- A setting on the Microphones page chooses the engine; left empty, the first one Home Assistant has is used.

## 0.5.3

- With camera sightings switched on, a vehicle seen on one camera could be pinned on a noise at any microphone, including one nowhere near it. The noise now has to be at the microphone of the camera that sees the vehicle.
- Each binary sensor remembers its last detection after it turns off: `last_heard`, `last_seconds`, `last_label`, `last_detail`, `last_mic`, `last_compass`, `last_conf`, `last_evidence` and `last_levels`.

## 0.5.2

- Volume slider beside Play on a recording. It is the same volume as live listening, so setting one sets the other, and it works while the recording plays.

## 0.5.1

- Far fewer false vehicles. A swell now has to stand clear of that microphone's own recent ups and downs, so leaves, water and gusts no longer count where they are the normal background. It must reach at least 6 dB, be heard at a second microphone as well, and is not reported while an aircraft that should be audible is on ADS-B.

## 0.5.0

- Vehicles are identified from sound alone. A pass-by is steady, pitchless noise that swells and falls away within 2 to 25 seconds; speech and barking come in bursts, sirens and birds have pitch, and machinery or rain starts and stays. It is placed by how far the swell rose at each microphone.
- Camera sightings no longer count as evidence for anything. A new setting on the Microphones page, "Let camera sightings support a sound", brings them back; it is off by default. Frigate's sound labels, BirdNET-Go, ADS-B and dispatch feeds are used as before.

## 0.4.2

- Passing vehicles were almost never reported: beside a Frigate sighting the sound still had to rise about 11 dB in the middle band. A moving car, truck, motorcycle or bus seen by Frigate now needs a rise of about 4 dB at any microphone, and low engine rumble counts as well as tyre noise. Sound alone is still not enough, so wind and voices are not logged as vehicles.

## 0.4.1

- A howl is no longer reported on sound alone. At night the sound's own score could just reach the reporting threshold, so a faint steady whine was logged as a coyote for twenty minutes. It now always needs support from Frigate or BirdNET-Go, and a tone has to be clearly louder than the microphone's background to count at all, for howls and sirens alike.
- New setting on the Microphones page: "Report a sound only when at least this sure" (50 to 95 %).

## 0.4.0

- Recordings: each sound keeps up to 30 seconds from the microphone that heard it best. Select a sound in the list or a chip to see the recording's spectrogram and play it as recorded; click the spectrogram to play from that point.
- Isolate: a switch on the same panel redraws the spectrogram with only that kind of sound's frequency band and with the microphone's steady background removed, and plays it through a matching band-pass.
- Recordings are held in temporary storage for the last 100 sounds, are never in a backup, and are cleared when Home Assistant restarts. A setting on the Microphones page turns them off.

## 0.3.2

- The integration has its own icon and logo: a location pin holding a waveform, between two sound arcs.

## 0.3.1

- The icon beside the title is back, as an option: `show_icon` (on by default) and `icon` (default `mdi:waveform`).

## 0.3.0

- Hyperbolic map: `radar: hyperbolic` is the fisheye map with a focus you can drag. Whatever you pull to the middle is magnified while the rest stays in view; the house button returns to the house.

## 0.2.4

- Street maps come through Home Assistant's own map tile proxy where the installed version has one, and otherwise straight from OpenStreetMap with the site's address sent as its servers require. CARTO, tried in 0.2.2, turned out to want an API key.
- card-mod and UIX styles now apply. The card's frame is created with the card and never rebuilt, so styles attached to it at creation are kept.
- A moving `garbage_truck` seen by Frigate counts as a vehicle.

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
