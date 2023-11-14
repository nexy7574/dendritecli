import hashlib
import hmac
import importlib.metadata
import logging
import secrets
import sys
import typing
from urllib.parse import quote
from pathlib import Path
from ._sql import SQLHandler

import httpx
import toml

try:
    import h2
except ImportError:
    h2 = None


log = logging.getLogger("dendritecli.api")
if (Path.home() / ".config").exists():
    CONFIG_FILE = Path.home() / ".config" / "dendritecli.toml"
else:
    CONFIG_FILE = Path.home() / ".dendritecli.toml"


if not CONFIG_FILE.exists():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.touch()


class BearerAuth(httpx.Auth):
    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request

    async def async_auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


__USER_AGENT__ = "dendritecli/{} httpx/{} python/{}".format(
    importlib.metadata.version("dendritecli"),
    importlib.metadata.version("httpx"),
    ".".join([str(x) for x in sys.version_info[:3]]),
)


class HTTPAPIManager:
    """
    APIManager is a class that manages the API requests to the dendrite server.
    """

    def __init__(self, access_token: str, client: typing.Optional[httpx.Client] = None, **kwargs):
        config = self.read_config()
        if config.get("proxies"):
            kwargs.setdefault("proxies", config["proxies"])
        if config.get("timeout"):
            kwargs.setdefault("timeout", config["timeout"])
        if config.get("headers"):
            kwargs.setdefault("headers", config["headers"])
        self.base_url = kwargs.get("server", config.get("server")) or "http://localhost:8008"
        self.client = client or httpx.Client(
            auth=BearerAuth(access_token),
            headers={
                **kwargs.pop("headers", {}),
                "User-Agent": __USER_AGENT__,
            },
            http2=h2 is not None,
            proxies=kwargs.pop("proxies", None),
            timeout=kwargs.pop("timeout", httpx.Timeout(connect=10, read=180, write=60, pool=10)),
            follow_redirects=True,
            max_redirects=10,
            base_url=self.base_url
        )

        self.fulltext_reindex = self.full_text_reindex = self.reindex_events

    @staticmethod
    def read_config() -> dict:
        """Reads the dendritecli.toml file and returns a dict"""
        if CONFIG_FILE.exists():
            log.debug(f"Reading config file: {CONFIG_FILE}")
            t = toml.load(CONFIG_FILE)
            log.debug(t)
            return t
        else:
            log.debug("Config file %s not found.", CONFIG_FILE)
            return {}

    @staticmethod
    def write_config(config: dict) -> None:
        """Writes the config dict to the config file"""
        log.debug(f"Writing config file: {CONFIG_FILE}")
        with open(CONFIG_FILE, "w") as f:
            toml.dump(config, f)

    def evacuate_room(self, room_id: str) -> dict[str, list[str]]:
        """
        Instruct Dendrite to part all local users from the given ``roomID`` in the URL.
        It may take some time to complete.
        A JSON body will be returned containing the user IDs of all affected users.

        If the room has an alias set (e.g. is published), the room’s ID will not be visible in the URL,
        but it can be found as the room’s “internal ID” in Element Web (Settings -> Advanced)

        Docs: https://matrix-org.github.io/dendrite/administration/adminapi#post-_dendriteadminevacuateroomroomid

        :param room_id: The room ID or alias to evacuate.
        :return: The result (``{"affected": ["@user1:example.com", "@user2:example.com"]}``)
        :raises: httpx.HTTPError - if the request failed.
        """
        log.info("Evacuating room %s", room_id)
        room_id = quote(room_id)
        response = self.client.post(f"/_dendrite/admin/evacuateRoom/{room_id}", timeout=None)
        log.info("Finished evacuating room %s", room_id)
        response.raise_for_status()
        return response.json()

    def evacuate_user(self, user_id: str) -> dict[str, list[str]]:
        """
        Instruct Dendrite to part the given local userID in the URL from all rooms which they are currently joined.
        A JSON body will be returned containing the room IDs of all affected rooms.

        Docs: https://matrix-org.github.io/dendrite/administration/adminapi#post-_dendriteadminevacuateuseruserid

        :param user_id: The user ID to evacuate
        :return: The result (``{"affected": ["!room1:example.com", "!room2:example.com"]}``)
        :raises: httpx.HTTPError - if the request failed.
        """
        log.info("Evacuating user %s", user_id)
        user_id = quote(user_id)
        response = self.client.post(f"/_dendrite/admin/evacuateUser/{user_id}", timeout=None)
        log.info("Finished evacuating user %s", user_id)
        response.raise_for_status()
        return response.json()

    def reset_password(self, user_id: str, *, new_password: str, logout_devices: bool = False) -> dict[str, bool]:
        """
        Instruct Dendrite to reset the password of the given local userID in the URL.
        A JSON body will be returned containing the result.

        Docs: https://matrix-org.github.io/dendrite/administration/adminapi#post-_dendriteadminresetpassworduserid

        :param user_id: The user ID to reset the password for.
        :param new_password: The new password.
        :param logout_devices: Whether to log out all devices and invalidate all tokens.
        :return: The result (``{"password_updated": true}``)
        :raises: httpx.HTTPError - if the request failed.
        """
        if self.read_config().get("override-password-length-check", False) is False:
            if len(new_password.encode("utf-8")) > 72:
                raise ValueError(
                    "Passwords cannot be more than 72 bytes. See: https://github.com/matrix-org/dendrite/issues/3012"
                )
        else:
            log.debug("Password length check is disabled.")

        log.info("Resetting password for user %s", user_id)
        response = self.client.post(
            f"/_dendrite/admin/resetPassword/{user_id}",
            json={
                "password": new_password,
                "logout_devices": logout_devices,
            },
        )
        log.info("Finished resetting password for user %s", user_id)
        response.raise_for_status()
        return response.json()

    def reindex_events(self) -> dict:
        """
        Instructs Dendrite to reindex all searchable events (``m.room.message``, ``m.room.topic`` and ``m.room.name``).
        An empty JSON body will be returned immediately.
        Indexing is done in the background, the server logs every 1000 events (or below) when they are being indexed.
        Once reindexing is done, you’ll see something along the lines
        ``Indexed 69586 events in 53.68223182s`` in your debug logs.

        Docs: https://matrix-org.github.io/dendrite/administration/adminapi#get-_dendriteadminfulltextreindex

        :returns: None, unless the server returned extra data.
        :raises: httpx.HTTPError - if the request failed.
        """
        log.info("Requesting dendrite to reindex events")
        response = self.client.post("/_dendrite/admin/fulltext/reindex")
        response.raise_for_status()
        return response.json() or None

    def refresh_devices(self, user_id: str) -> typing.Optional[dict]:
        """
        This endpoint instructs Dendrite to immediately query /devices/{userID} on a federated server.
        An empty JSON body will be returned on success, updating all locally stored user devices/keys.
        This can be used to possibly resolve E2EE issues, where the remote user can’t decrypt messages.

        Docs: https://matrix-org.github.io/dendrite/administration/adminapi#post-_dendriteadminrefreshdevicesuserid

        :param user_id: The user ID to refresh the devices for.
        :return: None, unless the server returned extra data.
        :raises: httpx.HTTPError - if the request failed.
        """
        log.info("Requesting dendrite to refresh devices for user %s", user_id)
        user_id = quote(user_id)
        response = self.client.post(f"/_dendrite/admin/refreshDevices/{user_id}")
        response.raise_for_status()
        return response.json()

    def purge_room(self, room_id: str) -> typing.Optional[dict]:
        """
        This endpoint instructs Dendrite to purge all events in a room.
        An empty JSON body will be returned on success.

        Docs: https://matrix-org.github.io/dendrite/administration/adminapi#post-_dendriteadminpurgeroomroomid

        :param room_id: The room ID to purge.
        :return: None, unless the server returned extra data.
        :raises: httpx.HTTPError - if the request failed.
        """
        log.info("Requesting dendrite to purge room %s", room_id)
        room_id = quote(room_id)
        response = self.client.post(f"/_dendrite/admin/purgeRoom/{room_id}")
        log.info("Finished purging room %s", room_id)
        response.raise_for_status()
        return response.json()

    def send_server_notice(self, user_id: str, message: dict) -> dict:
        """
        This endpoint instructs Dendrite to send a server notice to the given user.
        An empty JSON body will be returned on success.

        Docs: https://matrix-org.github.io/dendrite/administration/adminapi#post-_synapseadminv1send_server_notice
        :param user_id: The user ID to send the notice to.
        :param message: The message to send.
        :return: The event's response (usually ``{"event_id": "$event_id"}``)
        :raises: httpx.HTTPError - if the request failed.
        """
        log.info("Requesting dendrite to send a server notice to %s", user_id)
        response = self.client.post(
            "/_synapse/admin/v1/send_server_notice", json={"user_id": user_id, "content": message}
        )
        log.info("Finished sending server notice to %s", user_id)
        response.raise_for_status()
        return response.json()

    @typing.overload
    def register(self) -> str:
        """Fetches the nonce for shared-secret registration.

        Docs: https://matrix-org.github.io/synapse/latest/admin_api/register_api.html#shared-secret-registration
        :return: The nonce.
        :raises: httpx.HTTPError - if the request failed.
        """
        ...

    @typing.overload
    def register(
        self,
        nonce: str,
        *,
        shared_secret: str,
        username: str,
        displayname: str = None,
        password: str,
        admin: bool = False,
    ) -> dict:
        """Registers a new user with the given nonce.

        Docs: https://matrix-org.github.io/synapse/latest/admin_api/register_api.html#shared-secret-registration
        :param nonce: The nonce to use.
        :param shared_secret: The shared secret to use.
        :param username: The username to register.
        :param displayname: The display name to register. Defaults to username.
        :param password: The password to register.
        :param admin: Whether to register the user as an admin.
        :return: The response (``{"access_token": "...", "user_id": "...", "home_server": "...", "device_id": "..."}``).
        :raises: httpx.HTTPError - if the request failed.
        """
        ...

    def register(self, nonce: typing.Optional[str] = None, **kwargs) -> typing.Union[str, dict]:
        """
        Registers a new user with the given nonce.

        Docs: https://matrix-org.github.io/synapse/latest/admin_api/register_api.html
        """
        if nonce is None:
            log.info("Requesting nonce for shared-secret registration")
            response = self.client.get("/_synapse/admin/v1/register")
            log.info("Received nonce for shared-secret registration")
            response.raise_for_status()
            return response.json()["nonce"]
        else:
            if self.read_config().get("override-password-length-check", False) is False:
                if len(kwargs["password"].encode("utf-8")) > 72:
                    raise ValueError(
                        "Passwords cannot be more than 72 bytes. "
                        "See: https://github.com/matrix-org/dendrite/issues/3012"
                    )
            else:
                log.debug("Password length check is disabled.")
            log.info("Constructing HMAC for shared-secret registration")
            mac = hmac.new(kwargs["shared_secret"].encode("utf-8"), digestmod=hashlib.sha1)
            admin = "admin" if kwargs["admin"] else "notadmin"
            kwargs.setdefault("displayname", kwargs["username"])
            kwargs["admin"] = admin
            kwargs['nonce'] = nonce

            mac.update(kwargs["nonce"].encode("utf-8"))
            mac.update(b'\x00')
            mac.update(kwargs["username"].encode("utf-8"))
            mac.update(b'\x00')
            mac.update(kwargs["password"].encode("utf-8"))
            mac.update(b'\x00')
            mac.update(b'notadmin' if not kwargs["admin"] else b'admin')

            mac = mac.hexdigest()
            log.info("Registering user %s", kwargs["username"])
            response = self.client.post("/_synapse/admin/v1/register", json={**kwargs, "nonce": nonce, "mac": mac})
            log.info("Done registering user %s", kwargs["username"])
            response.raise_for_status()
            return response.json()

    def whois(self, user_id: str) -> dict:
        """
        Fetches information about a user.

        Docs:
            1. https://matrix-org.github.io/dendrite/administration/adminapi#get-_matrixclientv3adminwhoisuserid
            2. https://spec.matrix.org/v1.3/client-server-api/#get_matrixclientv3adminwhoisuserid

        :param user_id: The user ID to fetch information about.
        :return: The user's information (see docs).
        :raises: httpx.HTTPError - if the request failed.
        """
        log.info("Fetching information about user %s", user_id)
        user_id = quote(user_id)
        response = self.client.get(f"/_matrix/client/v3/admin/whois/{user_id}")
        log.info("Done fetching information about user %s", user_id)
        response.raise_for_status()
        return response.json()

    def deactivate(self, user_id: str) -> None:
        """
        Deactivates a user.

        Docs:
            - None. There isn't an official dendrite API to deactivate a user, so this function does the following:
                1. Reset the user's password.
                2. Users the user's new password to get an access token
                3. Uses the access token to deactivate the user.

            - Please make sure that the user was evacuated beforehand.

        :param user_id: The user ID to deactivate
        :return: If deactivation was successful
        :raises: httpx.HTTPError - if a request failed.
        :raises: RuntimeError - if the password reset failed.
        """
        log.info("Deactivating user (step 1): Resetting password for user %s", user_id)
        random_password = secrets.token_hex(32)
        log.debug("Selected random password %r for temporary reset.", random_password)
        response = self.reset_password(user_id, new_password=random_password)
        if response.get("password_updated") is not True:
            raise RuntimeError("Failed to reset password.")

        log.info("Deactivating user (step 2): Getting access token for user %s", user_id)
        response = self.client.post(
            "/_matrix/client/v3/login",
            json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": user_id},
                "password": random_password,
                "initial_device_display_name": "dendritecli",
            },
        )
        response.raise_for_status()
        access_token = response.json()["access_token"]
        log.debug("Got access token %r for user %r.", access_token, user_id)

        log.info("Beginning \"interactive\" deactivation of %s.", user_id)

        initial_response = self.client.post(
            "/_matrix/client/v3/account/deactivate",
            auth=BearerAuth(access_token),
        )
        # This should yield HTTP 401 with our expected flow.
        if initial_response.status_code != 401:
            log.error("Unexpected response code %r from deactivation endpoint.", initial_response.status_code)
            raise RuntimeError("Unexpected response code from deactivation endpoint.")

        info = initial_response.json()
        flows = info["flows"]
        for flow in flows:
            if not isinstance(flow, dict):
                log.debug("Unexpected flow value %r. Skipping.", flow)
            elif not isinstance(flow.get("stages"), list):
                log.debug("Unexpected flow stages value %r. Skipping.", flow)
            else:
                break
        else:
            raise RuntimeError("No supported flows found.")
        stages = flow["stages"]
        if stages[0] != "m.login.password":
            raise RuntimeError("First stage is not m.login.password.")
        body = {
            "auth": {
                "identifier": {"type": "m.id.user", "user": user_id},
                "password": random_password,
                "session": info["session"],
                "type": "m.login.password",
                "user": user_id,
            },
            "erase": True
        }
        log.info("Deactivating user (step 3): Deactivating user %s", user_id)
        response = self.client.post(
            "/_matrix/client/v3/account/deactivate",
            auth=BearerAuth(access_token),
            json=body,
        )
        response.raise_for_status()
        log.info("Done deactivating user %s", user_id)
        return

    def list_accounts(self, uri: str):
        """
        Lists all accounts registered in the database.

        :return: A list of user accounts and their profiles in one dictionary
        """
        with SQLHandler(uri) as sql:
            users = list(sql.list_accounts())
        return users
