import secrets
import json

import fastapi
from pydantic import BaseModel
from fastapi.responses import JSONResponse


class PasswordResetBody(BaseModel):
    password: str
    logout_devices: bool = False


app = fastapi.FastAPI(default_response_class=JSONResponse)
app.state.users = {
    "@example:example.local": {
        "rooms": [
            "!123456789abcdef:example.local",
        ],
        "password": "example.password",
        "access_token": "example.access_token",
    }
}
app.state.rooms = {
    "#example:example.local": {
        "users": [
            "@example:example.local",
        ],
    }
}


# @app.post("/_test/reset")
def reset_state():
    app.state.users = {
        "@example:example.local": {
            "rooms": [
                "#example:example.local",
            ],
            "password": "example.password",
        }
    }
    app.state.rooms = {
        "#example:example.local": {
            "users": [
                "@example:example.local",
            ],
        }
    }
    print("Reset app state:", app.state.users, app.state.rooms)


@app.post("/_dendrite/admin/evacuateRoom/{room_id}")
async def evacuate_room(room_id: str):
    if room_id not in app.state.rooms.keys():
        raise fastapi.HTTPException(status_code=404)

    affected = []
    for user in app.state.rooms[room_id]["users"].copy():
        app.state.users[user]["rooms"].remove(room_id)
        app.state.rooms[room_id]["users"].remove(user)
        affected.append(user)
    return {"affected": affected}


@app.post("/_dendrite/admin/evacuateUser/{user_id}")
async def evacuate_user(user_id: str):
    if user_id not in app.state.users.keys():
        raise fastapi.HTTPException(status_code=404)

    affected = []
    for room in app.state.users[user_id]["rooms"].copy():
        app.state.users[user_id]["rooms"].remove(room)
        app.state.rooms[room]["users"].remove(user_id)
        affected.append(room)
    return {"affected": affected}


@app.post("/_dendrite/admin/resetPassword/{user_id}")
async def reset_password(user_id: str, body: PasswordResetBody):
    if user_id not in app.state.users:
        raise fastapi.HTTPException(status_code=404)

    app.state.users[user_id]["password"] = body.password
    return {"password_updated": True}


@app.post("/_dendrite/admin/fulltext/reindex")
async def reindex():
    return {}


@app.post("/_dendrite/admin/refreshDevices/{user_id}")
async def refresh_devices(user_id: str):
    if user_id not in app.state.users:
        raise fastapi.HTTPException(status_code=404)

    return {}


@app.post("/_dendrite/admin/purgeRoom/{room_id}")
async def purge_room(room_id: str):
    if room_id not in app.state.rooms:
        raise fastapi.HTTPException(status_code=404)

    for user in app.state.rooms[room_id]["users"].copy():
        app.state.users[user]["rooms"].remove(room_id)
    app.state.rooms[room_id]["users"] = []
    return {}


@app.post("/_synapse/admin/v1/send_server_notice")
async def send_server_notice(req: fastapi.Request):
    data = await req.json()
    if "user_id" not in data:
        raise fastapi.HTTPException(status_code=400)
    if "content" not in data:
        raise fastapi.HTTPException(status_code=400)
    return {"event_id": "$" + secrets.token_urlsafe(16)}


@app.get("/_synapse/admin/v1/register")
async def register__get():
    return {"nonce": "nonce"}


@app.post("/_synapse/admin/v1/register")
async def register(req: fastapi.Request):
    body = await req.json()
    if body.get("nonce") != "nonce" or body.get("mac") is None:
        raise fastapi.HTTPException(status_code=400)

    # Assume, for the purposes of the test, the body is correct.
    # This is a mock server, after all.
    app.state.users[body["username"]] = {
        "rooms": [],
        "password": body["password"],
        "access_token": "example.access_token." + body["username"],
    }
    return {
        "access_token": "example.access_token." + body["username"],
        "home_server": "example.local",
        "user_id": body["username"],
        "device_id": "example.device_id." + body["username"],
    }


@app.get("/_matrix/client/v3/admin/whois/{user_id}")
async def whois(user_id: str):
    if user_id not in app.state.users:
        raise fastapi.HTTPException(status_code=404)
    return {
        "devices": [],
        "user_id": user_id,
    }


@app.post("/_matrix/client/v3/login")
async def login(req: fastapi.Request):
    body = await req.json()
    if body["type"] != "m.login.password":
        raise fastapi.HTTPException(status_code=400)
    if body["identifier"]["type"] != "m.id.user":
        raise fastapi.HTTPException(status_code=400)
    if body["identifier"]["user"] not in app.state.users:
        raise fastapi.HTTPException(status_code=400)
    if body["password"] != app.state.users[body["identifier"]["user"]]["password"]:
        raise fastapi.HTTPException(status_code=400)
    return {
        "access_token": app.state.users[body["identifier"]["user"]]["access_token"],
        "home_server": "example.local",
        "user_id": body["identifier"]["user"],
        "device_id": "example.device_id." + body["identifier"]["user"],
    }


@app.post("/_matrix/client/v3/account/deactivate")
async def account_deactivate(req: fastapi.Request):
    try:
        body = await req.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {
                "flows": [
                    {
                        "stages": ["m.login.password"],
                    }
                ],
                "session": "session_id",
            },
            401,
        )

    if not body.get("auth"):
        return JSONResponse(
            {
                "flows": [
                    {
                        "stages": ["m.login.password"],
                    }
                ],
                "session": "session_id",
            },
            401,
        )

    if body["auth"].get("session") != "session_id":
        return JSONResponse(
            {
                "flows": [
                    {
                        "stages": ["m.login.password"],
                    }
                ],
                "session": "session_id",
            },
            401,
        )

    if body["auth"].get("type") != "m.login.password":
        return JSONResponse(
            {
                "flows": [
                    {
                        "stages": ["m.login.password"],
                    }
                ],
                "session": "session_id",
            },
            401,
        )
    return {}
