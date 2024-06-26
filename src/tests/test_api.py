from dendritecli.api import HTTPAPIManager
from ._mock_server import app, reset_state
import pytest
import httpx
from fastapi.testclient import TestClient


manager = HTTPAPIManager("example.access_token", TestClient(app))


@pytest.mark.dependency()
def test_registration():
    nonce = manager.register()
    assert nonce == "nonce", "invalid test nonce."
    manager.register(nonce=nonce, shared_secret="shared_secret", username="username", password="password", admin=True)
    reset_state()


@pytest.mark.parametrize(
    "room_id,expected_json,expected_err",
    [
        ["#example:example.local", {"affected": ["@example:example.local"]}, None],
        ["!doesntexist:example.local", None, httpx.HTTPStatusError],
    ],
)
def test_evacuate_room(room_id: str, expected_json, expected_err):
    reset_state()
    if expected_err:
        with pytest.raises(expected_err):
            manager.evacuate_room(room_id)
        return
    result = manager.evacuate_room(room_id)
    assert result == expected_json, "invalid result."
    reset_state()


@pytest.mark.parametrize(
    "room_id,expected_json,expected_err",
    [
        ["@example:example.local", {"affected": ["#example:example.local"]}, None],
        ["@doesntexist:example.local", None, httpx.HTTPStatusError],
    ],
)
def test_evacuate_user(room_id: str, expected_json, expected_err):
    reset_state()
    if expected_err:
        with pytest.raises(expected_err):
            manager.evacuate_user(room_id)
        return
    result = manager.evacuate_user(room_id)
    assert result == expected_json, "invalid result."
    reset_state()


def test_reindex_events():
    assert manager.reindex_events() is None, "result not empty"
    reset_state()


@pytest.mark.parametrize(
    "user_id,expected_err", [["@example:example.local", None], ["@doesntexist:example.local", httpx.HTTPStatusError]]
)
def test_refresh_devices(user_id: str, expected_err):
    reset_state()
    if expected_err:
        with pytest.raises(expected_err):
            manager.refresh_devices(user_id)
        return
    assert manager.refresh_devices(user_id) == {}, "result not empty"
    reset_state()


@pytest.mark.parametrize(
    "room_id,expected_err", [["#example:example.local", None], ["#doesntexist:example.local", httpx.HTTPStatusError]]
)
def test_purge_room(room_id, expected_err):
    reset_state()
    if expected_err:
        with pytest.raises(expected_err):
            manager.purge_room(room_id)
        return
    assert manager.purge_room(room_id) == {}, "result not empty"
    reset_state()


@pytest.mark.parametrize(
    "user_id,content,expected_err",
    [
        ["@example:example.local", {"content": "content"}, None],
        ["@doesntexist:example.local", {"content": "content"}, None],
    ],
)
def test_send_server_notice(user_id: str, content: dict, expected_err):
    reset_state()
    assert manager.send_server_notice(user_id, content).get("event_id"), "no event id"
    reset_state()


@pytest.mark.dependency(depends=["test_registration"])
def test_deactivation():
    nonce = manager.register()
    user = manager.register(
        nonce=nonce, shared_secret="shared_secret", username="username", password="password", admin=True
    )
    assert manager.deactivate(user["user_id"]) is None, "result not empty"
