"""Constants for Soundscape."""
DOMAIN = "soundscape"
VERSION = "0.3.0"
EVENT = "soundscape_event"

CONF_FRIGATE_URL = "frigate_url"
CONF_CAMERAS = "cameras"
CONF_TEMPLATE = "stream_template"
CONF_OVERRIDES = "stream_overrides"
CONF_BIRDNET_URL = "birdnet_url"
CONF_ADSB = "adsb_provider"
CONF_ADSB_URL = "adsb_url"
CONF_ADSB_RADIUS = "adsb_radius_km"
CONF_DISPATCH = "dispatch"
CONF_IGNORE = "ignore"
CONF_GEOMETRY = "geometry"
CONF_UNITS = "units"

DEFAULT_TEMPLATE = "rtsp://{host}:8554/{camera}"
SAMPLE_RATE = 24000

ADSB_PROVIDERS = {
    "adsb.fi": "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}",
    "adsb.lol": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}",
    "airplanes.live": "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}",
}
TYPES_URL = "https://raw.githubusercontent.com/wiedehopf/tar1090-db/master/db/icao_aircraft_types2.js"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = f"HomeAssistant-Soundscape/{VERSION} (+https://github.com/FortranFour/soundscape)"

# Classes that get a binary sensor. "aircraft" is on for any kind of aircraft.
SENSOR_CLASSES = ("siren", "coyote", "dog", "bird", "vehicle", "car_alarm", "glass", "bang",
                  "alarm", "aircraft", "helicopter", "tiltrotor")
