import ast
import importlib.util
import json
import sys
import tempfile
import threading
import types
import urllib.error
from pathlib import Path


root = Path(sys.argv[1])
for path in root.rglob("*.py"):
    ast.parse(path.read_text(encoding="utf-8"))

manifest = (root / "addon.xml").read_text(encoding="utf-8")
assert 'version="1.0.0"' in manifest
assert 'library="default.py"' in manifest
assert "resources/icon.png" in manifest
assert (root / "resources" / "icon.png").is_file()

profile = tempfile.TemporaryDirectory()
settings = {
    "api_url": "https://example.invalid/api/kodi/v1",
    "access_token": "fake",
    "enabled": True,
    "resume_enabled": False,
    "completion_threshold": 90,
    "progress_sync_interval": 30,
}
notifications = []


class Addon:
    def getAddonInfo(self, key):
        return {
            "path": str(root),
            "profile": profile.name,
            "version": "1.0.0",
        }[key]

    def getSettingString(self, key):
        return str(settings.get(key, ""))

    def getSettingBool(self, key):
        return bool(settings.get(key, False))

    def getSettingInt(self, key):
        return settings.get(key, 0)

    def setSettingString(self, key, value):
        settings[key] = value

    def getLocalizedString(self, key):
        return ""

    def openSettings(self):
        return None


class Dialog:
    def notification(self, *args, **kwargs):
        notifications.append((args, kwargs))
        return None

    def ok(self, *args, **kwargs):
        return None

    def select(self, *args, **kwargs):
        return -1

    def input(self, *args, **kwargs):
        return ""

    def yesno(self, *args, **kwargs):
        return False


sys.modules["xbmcaddon"] = types.SimpleNamespace(Addon=Addon)
sys.modules["xbmc"] = types.SimpleNamespace(
    LOGINFO=1,
    LOGWARNING=2,
    LOGDEBUG=0,
    log=lambda *args: None,
    getInfoLabel=lambda key: "Kodi Test",
    Monitor=object,
)
sys.modules["xbmcgui"] = types.SimpleNamespace(
    Dialog=Dialog,
    INPUT_ALPHANUM=0,
)
sys.modules["xbmcvfs"] = types.SimpleNamespace(
    translatePath=lambda value: value,
    mkdirs=lambda value: None,
)
sys.path.insert(0, str(root / "resources" / "lib"))

import api
import playback

http_post_progress = api._post_progress

service_spec = importlib.util.spec_from_file_location(
    "replay_service", root / "service.py"
)
service = importlib.util.module_from_spec(service_spec)
service_spec.loader.exec_module(service)


def item(identifier, percentage, watched=False):
    return {
        "mediaType": "movie",
        "tmdbId": identifier,
        "percentage": percentage,
        "positionSeconds": percentage * 10,
        "durationSeconds": 1000,
        "watched": watched,
    }


# HTTPS validation prevents sending a device token to an unsafe endpoint.
assert api.get_api_base_url() == "https://example.invalid/api/kodi/v1"
settings["api_url"] = "http://example.invalid/api/kodi/v1"
assert api.get_api_base_url() == ""
settings["api_url"] = "https://user:pass@example.invalid/api/kodi/v1"
assert api.get_api_base_url() == ""
settings["api_url"] = "https://example.invalid/api/kodi/v1"

# TMDb season zero represents specials and must remain a valid identity.
special = playback.build_payload(
    {
        "type": "episode",
        "uniqueid": {"tmdb": "1399"},
        "season": 0,
        "episode": 2,
        "showtitle": "Specials",
    }
)
assert special and special["season"] == 0 and special["episode"] == 2

# A newer live save retires stale queued data for the same title.
api._write_outbox([item(1, 10)])
sent = []
api._post_progress = lambda base, token, payload: (
    sent.append(payload) or True,
    False,
)
assert api.sync_progress(item(1, 50))
assert sent[-1]["percentage"] == 50 and api._read_outbox() == []

# A queued completion cannot be overwritten by a later partial update.
sent.clear()
api._write_outbox([item(1, 100, True)])
assert api.sync_progress(item(1, 20))
assert len(sent) == 1 and sent[0]["watched"]

# Retry is bounded at the first network/auth failure.
api._write_outbox([item(identifier, 10) for identifier in range(1, 101)])
calls = []
api._post_progress = lambda *args: (calls.append(1) and False, True)
assert not api.flush_pending_progress()
assert len(calls) == 1 and len(api._read_outbox()) == 100

# Queue and flush operations remain serialized.
api._write_outbox([item(1, 10)])
entered = threading.Event()
release = threading.Event()


def slow_post(*args):
    entered.set()
    assert release.wait(3)
    return True, False


api._post_progress = slow_post
flush_thread = threading.Thread(target=api.flush_pending_progress)
flush_thread.start()
assert entered.wait(2)
queue_thread = threading.Thread(target=lambda: api.queue_progress(item(2, 40)))
queue_thread.start()
release.set()
flush_thread.join(3)
queue_thread.join(3)
assert not flush_thread.is_alive() and not queue_thread.is_alive()
assert api._read_outbox() == [item(2, 40)]

# The stop event from the old title cannot complete the newly started title.
tracker = service.PlaybackTracker()
tracker.payload = item(1, 10)
tracker.signature = "old"
tracker.source_key = ("old",)
tracker.playing_file = "old.mkv"
tracker.position_seconds = 120
tracker.duration_seconds = 1000
tracker.player_active = True
tracker._active_video_player_id = lambda: 1
tracker._payload_for_item = lambda current: (None, None)
saved = []
service.sync_progress = lambda payload: saved.append(payload) or True
service.json_rpc = lambda method, params: (
    {"item": {"file": "new.mkv"}}
    if method == "Player.GetItem"
    else {"time": {"seconds": 30}, "totaltime": {"minutes": 20}}
)
tracker.poll()
assert tracker.payload is None and saved and saved[0]["tmdbId"] == 1


class Response:
    def __init__(self, body=b"{}", status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


# Linking from the TV panel stores the token and consumes the one-time code.
settings["access_token"] = ""


def expired_code_open(*args, **kwargs):
    raise urllib.error.HTTPError("https://example.invalid", 401, "", {}, None)


api.urllib.request.urlopen = expired_code_open
linked, reason = api.connect_with_code("A1B2C3D4E5")
assert not linked and reason == "link_failed" and settings["link_code"] == ""

api.urllib.request.urlopen = lambda *args, **kwargs: Response(
    json.dumps({"token": "linked-token"}).encode("utf-8")
)
linked, reason = api.connect_with_code("A1B2C3D4E5")
assert linked and not reason
assert settings["access_token"] == "linked-token"
assert settings["link_code"] == ""

# The health check uses the authenticated device endpoint.
requested_urls = []


def successful_open(request, **kwargs):
    requested_urls.append(request.full_url)
    return Response()


api.urllib.request.urlopen = successful_open
ok, reason = api.test_connection()
assert ok and not reason and requested_urls[-1].endswith("/device")

# A rejected token is cleared while unsent progress remains queued for relink.
api._write_outbox([])


def unauthorized_open(*args, **kwargs):
    raise urllib.error.HTTPError("https://example.invalid", 401, "", {}, None)


api.urllib.request.urlopen = unauthorized_open
settings["access_token"] = "expired-token"
api._post_progress = http_post_progress
assert not api.sync_progress(item(55, 25))
assert settings["access_token"] == ""
assert api._read_outbox() == [item(55, 25)]

# Remote disconnect revokes credentials and preserves the offline queue.
settings["access_token"] = "linked-token"
api.urllib.request.urlopen = lambda *args, **kwargs: Response()
disconnected, reason = api.disconnect_device()
assert disconnected and not reason
assert settings["access_token"] == ""
assert api._read_outbox() == [item(55, 25)]

# Diagnostics never expose the token and include the release identity.
settings["access_token"] = "diagnostic-token"
status = api.get_sync_status()
assert status["linked"] and status["enabled"] and status["version"] == "1.0.0"
assert status["apiConfigured"] and isinstance(status["pendingCount"], int)
assert "access_token" not in status

panel_spec = importlib.util.spec_from_file_location(
    "replay_panel", root / "default.py"
)
panel = importlib.util.module_from_spec(panel_spec)
panel_spec.loader.exec_module(panel)
message = panel.status_message(status)
assert "Kodi Test" in message and "diagnostic-token" not in message

# Every installed release is announced only once, even when the service restarts.
notice_count = len(notifications)
assert service.notify_release_if_needed()
assert not service.notify_release_if_needed()
assert len(notifications) == notice_count + 1
assert "1.0.0" in notifications[-1][0][1]

print(
    "PASS Kodi 1.0: syntax; package metadata; HTTPS guard; specials; "
    "stale queue; completion preservation; bounded retries; concurrent flush; "
    "sequential playback; panel link; device health; expired token; disconnect; "
    "diagnostics; release notice"
)
profile.cleanup()
