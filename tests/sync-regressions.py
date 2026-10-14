import ast
import importlib.util
import json
import sys
import tempfile
import threading
import types
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path


root = Path(sys.argv[1])
for path in root.rglob("*.py"):
    ast.parse(path.read_text(encoding="utf-8"))

manifest = (root / "addon.xml").read_text(encoding="utf-8")
assert 'version="1.4.0"' in manifest
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
    "library_sync_enabled": True,
    "library_sync_interval": 300,
    "notify_updates": True,
    "notify_sync": True,
    "notify_content": True,
}
notifications = []
executed_builtins = []


class Addon:
    def getAddonInfo(self, key):
        return {
            "path": str(root),
            "profile": profile.name,
            "version": "1.4.0",
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
    executebuiltin=lambda command: executed_builtins.append(command),
    executeJSONRPC=lambda query: json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
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
import library_sync
import playback
import updates

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
assert status["linked"] and status["enabled"] and status["version"] == "1.4.0"
assert status["apiConfigured"] and isinstance(status["pendingCount"], int)
assert "access_token" not in status

panel_spec = importlib.util.spec_from_file_location(
    "replay_panel", root / "default.py"
)
panel = importlib.util.module_from_spec(panel_spec)
panel_spec.loader.exec_module(panel)
message = panel.status_message(status)
assert "Kodi Test" in message and "diagnostic-token" not in message
assert "1.4.0" in panel.TITLE and "1.4.0" in message

# Every installed release is announced only once, even when the service restarts.
notice_count = len(notifications)
assert service.notify_release_if_needed()
assert not service.notify_release_if_needed()
assert len(notifications) == notice_count + 1
assert "1.4.0" in notifications[-1][0][1]

# Every Kodi 21 setting contains the required control declaration.
settings_root = ET.parse(root / "resources" / "settings.xml").getroot()
for setting in settings_root.findall(".//setting"):
    assert setting.find("control") is not None, setting.get("id")

# Replay manages only matching Kodi library items and can undo its own changes.
local_movies = {
    1: {"movieid": 1, "uniqueid": {"tmdb": "10"}, "playcount": 0},
    2: {"movieid": 2, "uniqueid": {"tmdb": "99"}, "playcount": 1},
}
local_episodes = {
    5: {
        "episodeid": 5,
        "tvshowid": 7,
        "season": 1,
        "episode": 2,
        "playcount": 0,
    }
}
library_calls = []


def library_rpc(method, params=None):
    if method == "VideoLibrary.GetMovies":
        return {"movies": list(local_movies.values())}
    if method == "VideoLibrary.GetTVShows":
        return {"tvshows": [{"tvshowid": 7, "uniqueid": {"tmdb": "20"}}]}
    if method == "VideoLibrary.GetEpisodes":
        return {"episodes": list(local_episodes.values())}
    library_calls.append((method, dict(params or {})))
    if method == "VideoLibrary.SetMovieDetails":
        local_movies[params["movieid"]]["playcount"] = params["playcount"]
        return "OK"
    if method == "VideoLibrary.SetEpisodeDetails":
        local_episodes[params["episodeid"]]["playcount"] = params["playcount"]
        return "OK"
    return None


first_snapshot = {
    "completedMovies": [{"tmdbId": 10}],
    "watchedEpisodes": [{"tmdbId": 20, "season": 1, "episode": 2}],
}
first_stats = library_sync.apply_snapshot(first_snapshot, library_rpc)
assert first_stats["changed"] == 2 and first_stats["watched"] == 2
assert local_movies[2]["playcount"] == 1
second_stats = library_sync.apply_snapshot(
    {"completedMovies": [], "watchedEpisodes": []},
    library_rpc,
)
assert second_stats["changed"] == 2 and second_stats["unwatched"] == 2
assert local_movies[2]["playcount"] == 1

# Content and update notices are deduplicated per device.
content_alert = {"key": "20:200:2026-10-15", "seriesTitle": "Serie"}
assert api.claim_content_notices([content_alert]) == [content_alert]
assert api.claim_content_notices([content_alert]) == []
updates.fetch_available_version = lambda: "1.5.0"
update_notice_count = len(notifications)
update_ok, update_result = updates.check_for_updates(notify=True)
assert update_ok and update_result["updateAvailable"]
assert updates.check_for_updates(notify=True)[0]
assert len(notifications) == update_notice_count + 1
status = api.get_sync_status()
assert status["availableVersion"] == "1.5.0" and status["updateAvailable"]

# Every Kodi startup asks enabled repositories for fresh add-on metadata.
assert service.request_addon_updates()
assert executed_builtins == ["UpdateAddonRepos"]

print(
    "PASS Kodi 1.4: syntax; package metadata; Kodi 21 settings; HTTPS guard; specials; "
    "stale queue; completion preservation; bounded retries; concurrent flush; "
    "sequential playback; panel link; device health; expired token; disconnect; "
    "diagnostics; visible version; release notice; bidirectional library state; "
    "safe unmanaged items; content dedupe; update centre; startup update check"
)
profile.cleanup()
