"""Constants for the Newlab LED integration."""

DOMAIN = "newlab"

# Cloud endpoints
BASE_URL = "https://smarthome.newlablight.com"
WELCOME_URL = f"{BASE_URL}/registrationwelcome"
LOGIN_URL = f"{BASE_URL}/registrationlogin"
HOME_URL = f"{BASE_URL}/registrationhome"
CONTROL_URL = f"{BASE_URL}/smarthome/newplantsendcommand"
REFRESH_URL = f"{BASE_URL}/smarthome/plantrefresh"

# Config entry keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_POLL_INTERVAL = "poll_interval"

# Defaults
DEFAULT_POLL_INTERVAL = 10  # seconds
MIN_POLL_INTERVAL = 5
MAX_POLL_INTERVAL = 60

# HTTP — neutral Accept-Language so Newlab returns default page language
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en;q=0.9,*;q=0.8",
}

# Timeouts
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 15

# Generic fallback name when the HTML has no label for a group.
# Template: use .format(gid=<int>).  Example result: "Group 3"
# Users can rename entities in HA at any time; unique_id is always stable.
GROUP_NAME_FALLBACK = "Group {gid}"

# Data keys stored in hass.data[DOMAIN]
DATA_COORDINATOR = "coordinator"
DATA_API = "api"

# Max HTML chars dumped to log at DEBUG level (avoids flooding the log file)
DEBUG_HTML_MAX_CHARS = 4000
