"""Safe, opt-in browser-session authentication for media extraction.

JaneConverter never asks for or stores a user's password. When selected, the
browser session is handed directly to yt-dlp for the active job.
"""

import os
from dataclasses import dataclass
from typing import Mapping

from typing import Optional, Tuple


PUBLIC_SESSION_LABEL = "Public only"
BROWSER_SESSION_CHOICES = (
    PUBLIC_SESSION_LABEL,
    "Chrome",
    "Edge",
    "Firefox",
    "Brave",
    "Vivaldi",
)

_BROWSER_ALIASES = {
    "none": None,
    "public": None,
    "public only": None,
    "chrome": "chrome",
    "edge": "edge",
    "firefox": "firefox",
    "brave": "brave",
    "vivaldi": "vivaldi",
    "opera": "opera",
    "chromium": "chromium",
    "safari": "safari",
}

_DEFAULT_BROWSER_PROGIDS = {
    "chromehtml": "chrome",
    "mseedgehtm": "edge",
    "firefoxurl": "firefox",
    "bravehtml": "brave",
    "vivaldihtm": "vivaldi",
    "vivaldiurl": "vivaldi",
    "operastable": "opera",
    "operagxstable": "opera",
}

_BROWSER_SIGNAL_MARKERS = (
    ("vivaldi", "vivaldi"),
    ("brave", "brave"),
    ("firefox", "firefox"),
    ("msedge", "edge"),
    ("microsoftedge", "edge"),
    ("chrome", "chrome"),
    ("opera", "opera"),
)


@dataclass(frozen=True)
class BrowserDetection:
    """Browser identity observed from the temporary localhost request."""

    label: str
    session_browser: Optional[str]
    user_agent: str = ""


def detect_browser_from_headers(headers: Mapping[str, str]) -> BrowserDetection:
    """Identify the browser that opened the access link from request headers.

    Browser client hints are checked along with the traditional user-agent so
    Chromium derivatives such as Vivaldi and Brave can be identified when they
    advertise their brand. This identifies the browser only; it never grants
    access or reads credentials.
    """
    user_agent = str(headers.get("User-Agent", "") or "")
    client_hints = " ".join(
        str(headers.get(name, "") or "")
        for name in ("Sec-CH-UA", "Sec-CH-UA-Full-Version-List", "Sec-CH-UA-Platform")
    )
    signal = f"{client_hints} {user_agent}".lower()

    browser_signals = (
        ("vivaldi", "Vivaldi", "vivaldi"),
        ("brave", "Brave", "brave"),
        ("edg/", "Microsoft Edge", "edge"),
        ("edga/", "Microsoft Edge", "edge"),
        ("edgios/", "Microsoft Edge", "edge"),
        ("opr/", "Opera", "opera"),
        ("opera", "Opera", "opera"),
        ("firefox", "Firefox", "firefox"),
        ("fxios", "Firefox", "firefox"),
        ("crios", "Google Chrome", "chrome"),
        ("chrome", "Google Chrome", "chrome"),
        ("chromium", "Chromium", "chromium"),
        ("safari", "Safari", "safari"),
    )
    for marker, label, session_browser in browser_signals:
        if marker in signal:
            # Safari appears in many Chromium user-agents; it is only Safari
            # when no Chromium-family marker was present.
            if label == "Safari" and any(token in signal for token in ("chrome", "chromium", "edg/", "opr/")):
                continue
            return BrowserDetection(label, session_browser, user_agent)
    return BrowserDetection("Unrecognized browser", None, user_agent)


def normalize_browser_session(selection: Optional[str]) -> Optional[str]:
    """Normalize a UI or CLI browser selection to yt-dlp's browser name."""
    key = str(selection or "none").strip().lower()
    if key not in _BROWSER_ALIASES:
        supported = ", ".join(BROWSER_SESSION_CHOICES)
        raise ValueError(f"Unsupported browser session '{selection}'. Choose from: {supported}")
    return _BROWSER_ALIASES[key]


def browser_session_label(selection: Optional[str]) -> str:
    """Return the stable user-facing label for a browser selection."""
    browser = normalize_browser_session(selection)
    return PUBLIC_SESSION_LABEL if browser is None else browser.title()


def yt_dlp_cookie_option(selection: Optional[str]) -> Optional[Tuple[str, None, None, None]]:
    """Build yt-dlp's in-memory browser-cookie option without creating a file."""
    browser = normalize_browser_session(selection)
    if browser is None:
        return None
    # yt-dlp accepts (browser, profile, keyring, container). Leaving the
    # optional values empty lets it select the user's default profile.
    return (browser, None, None, None)


def detect_default_browser_session() -> Optional[str]:
    """Return the yt-dlp browser name associated with Windows' default browser.

    The registry lookup is intentionally read-only. Unknown browsers are
    treated as public-only rather than guessing a profile or opening files.
    """
    if os.name != "nt":
        return None

    for signal in _windows_default_browser_signals():
        browser = _browser_from_signal(signal)
        if browser:
            return browser
    return None


def _browser_from_signal(signal: Optional[str]) -> Optional[str]:
    """Map a Windows ProgId or association command to a yt-dlp browser name."""
    normalized = str(signal or "").strip().lower()
    if not normalized:
        return None
    if normalized in _DEFAULT_BROWSER_PROGIDS:
        return _DEFAULT_BROWSER_PROGIDS[normalized]
    for marker, browser in _BROWSER_SIGNAL_MARKERS:
        if marker in normalized:
            return browser
    return None


def _windows_default_browser_signals() -> list[str]:
    """Read several Windows association locations, in preference order."""
    try:
        import winreg
    except ImportError:
        return []

    signals = []
    user_choice_root = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations"
    for scheme in ("https", "http"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{user_choice_root}\\{scheme}\\UserChoice") as key:
                value, _ = winreg.QueryValueEx(key, "ProgId")
            signals.append(str(value))
        except OSError:
            pass

    # Some Windows configurations omit UserChoice but still expose the actual
    # command used for HTTP/HTTPS. HKCR also includes per-user class overrides.
    user_association_paths = (
        r"Software\Classes\https\shell\open\command",
        r"Software\Classes\http\shell\open\command",
    )
    for path in user_association_paths:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value, _ = winreg.QueryValueEx(key, "")
            signals.append(str(value))
        except OSError:
            pass

    for scheme in ("https", "http"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{scheme}\\shell\\open\\command") as key:
                value, _ = winreg.QueryValueEx(key, "")
            signals.append(str(value))
        except OSError:
            pass
    return signals
