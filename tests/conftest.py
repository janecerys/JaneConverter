"""
Shared test fixtures and helpers for the JaneConverter test suite.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeResponse:
    """Minimal stand-in for requests.Response used by hermetic extractor tests."""

    def __init__(self, status_code=200, text="", json_data=None, content=b""):
        self.status_code = status_code
        self.text = text
        self._json = json_data if json_data is not None else {}
        self.content = content

    def json(self):
        return self._json


def make_spotify_track_embed_html(entity: dict) -> str:
    """Builds an embed page payload shaped like Spotify's __NEXT_DATA__ JSON."""
    import json
    payload = {
        "props": {
            "pageProps": {
                "state": {
                    "data": {
                        "entity": entity
                    }
                }
            }
        }
    }
    # Include a '<' inside the JSON to prove the DOTALL regex tolerates it
    return (
        '<html><head>'
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        '</head><body>track &amp; album</body></html>'
    )


def make_spotify_entity(**overrides) -> dict:
    entity = {
        "title": "Hyperpop Anthem",
        "artists": [{"name": "project//aspyr"}, {"name": "kvnokishi"}],
        "subtitle": "project//aspyr",
        "releaseDate": {"isoString": "2026-03-14T00:00:00Z"},
        "visualIdentity": {
            "image": [
                {"maxWidth": 320, "url": "https://image-cdn.example/small.jpg"},
                {"maxWidth": 640, "url": "https://image-cdn.example/large.jpg"},
            ]
        },
    }
    entity.update(overrides)
    return entity
