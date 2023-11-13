import secrets

import fastapi
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import time


class PasswordResetBody(BaseModel):
    password: str
    logout_devices: bool = False


app = fastapi.FastAPI(
    default_response_class=JSONResponse
)
app.state.users = {
    "@example:example.local": {
        "rooms": ["#example:example.local",],
        "password": "example.password"
    }
}
app.state.rooms = {
    "#example:example.local": {
        "users": ["@example:example.local",],
    }
}


@app.post("/_test/reset")
def reset_state():
    app.state.users = {
        "@example:example.local": {
            "rooms": ["#example:example.local", ],
            "password": "example.password"
        }
    }
    app.state.rooms = {
        "#example:example.local": {
            "users": ["@example:example.local", ],
        }
    }


@app.post("/_dendrite/admin/evacuateRoom/{room_id}")
def evacuate_room(room_id: str):
    if room_id not in app.state.rooms:
        raise fastapi.HTTPException(status_code=404)

    affected = []
    for user in app.state.rooms[room_id]["users"].copy():
        app.state.users[user]["rooms"].remove(room_id)
        app.state.rooms[room_id]["users"].remove(user)
        affected.append(user)
    return {"affected": affected}


@app.post("/_dendrite/admin/evacuateUser/{user_id}")
def evacuate_user(user_id: str):
    if user_id not in app.state.users:
        raise fastapi.HTTPException(status_code=404)

    affected = []
    for room in app.state.users[user_id]["rooms"].copy():
        app.state.users[user_id]["rooms"].remove(room)
        app.state.rooms[room]["users"].remove(user_id)
        affected.append(room)
    return {"affected": affected}


@app.post("/_dendrite/admin/resetPassword/{user_id}")
def reset_password(user_id: str, body: PasswordResetBody):
    if user_id not in app.state.users:
        raise fastapi.HTTPException(status_code=404)

    app.state.users[user_id]["password"] = body.password
    return {"password_updated": True}


@app.post("/_dendrite/admin/fulltext/reindex")
def reindex():
    return {}


@app.post("/_dendrite/admin/refreshDevices/{user_id}")
def refresh_devices(user_id: str):
    if user_id not in app.state.users:
        raise fastapi.HTTPException(status_code=404)

    return {}


@app.post("/_dendrite/admin/purgeRoom/{room_id}")
def purge_room(room_id: str):
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


@app.post("/_synapse/admin/v1/register")
async def register()
