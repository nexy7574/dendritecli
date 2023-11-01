import getpass
import logging
import pathlib
import secrets

import click
import rich
from rich.logging import RichHandler
from rich.prompt import Confirm, Prompt

from . import api

log = logging.getLogger("dendritecli.runtime")
console = rich.get_console()


@click.group()
@click.option(
    "--server", "-s", default=None, help="Dendrite server URL. Defaults to the one in the configuration file."
)
@click.option(
    "--config",
    "-c",
    default=api.CONFIG_FILE,
    help="Config file to use",
    type=click.Path(
        exists=True, readable=True, writable=True, resolve_path=True, allow_dash=True, path_type=pathlib.Path
    ),
)
@click.option(
    "--log-level",
    "-l",
    default="INFO",
    help="Log level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
)
@click.option(
    "--access-token",
    "-t",
    default=None,
    help="Access token to use. Default reads from config file, or prompts.",
)
@click.pass_context
def main(ctx: click.Context, server: str | None, config: pathlib.Path, log_level: str, access_token: str | None):
    """Manage the dendrite API from your cozy command line."""
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    api.CONFIG_FILE = config
    config = api.HTTPAPIManager.read_config()

    if access_token is None:
        access_token = config.get("access_token") or getpass.getpass("Access token: ")
    config["access_token"] = access_token
    if server:
        config["server"] = server
    else:
        server = config.get("server")
    api.HTTPAPIManager.write_config(config)
    ctx.obj = api.HTTPAPIManager(access_token=access_token, server=server)


@main.group()
def evacuate():
    """Evacuation management."""


@evacuate.command()
@click.argument("room_id")
@click.pass_obj
def room(http: api.HTTPAPIManager, room_id: str):
    """
    Evacuate a room. Removes all local users from the room.

    ROOM_ID should be the room ID to evacuate.
    """
    if not Confirm.ask("This will remove all users in the room. Are you sure?"):
        return False
    with console.status("Evacuating room..."):
        result = http.evacuate_room(room_id)
    console.print("[green]Evacuated room.")
    if len(result["affected"]) > 0:
        console.print(f"[yellow]Affected users:")
        for user in result["affected"]:
            console.print(f"[yellow]\t{user}")
    else:
        console.print("[yellow]No users were affected.")
    return True


@evacuate.command()
@click.argument("user_id")
@click.pass_obj
def user(http: api.HTTPAPIManager, user_id: str):
    """
    Evacuate a user. Removes the user from all local rooms.

    USER_ID should be the fully qualified (@username:domain.tld) user ID to evacuate.
    """
    if not Confirm.ask("This will remove the user from all local rooms. Are you sure?"):
        return
    with console.status("Evacuating user..."):
        result = http.evacuate_user(user_id)
    console.print("[green]Evacuated user.")
    if len(result["affected"]) > 0:
        console.print(f"[yellow]Affected rooms:")
        for _room in result["affected"]:
            console.print(f"[yellow]\t{_room}")
    else:
        console.print("[yellow]No rooms were affected.")


@main.command(name="reset-password")
@click.option(
    "--logout-devices",
    "-L",
    is_flag=True,
    help="Logout all devices after password reset and resets all login tokens.",
)
@click.argument("user_id")
@click.pass_obj
def reset_password(http: api.HTTPAPIManager, logout_devices: bool, user_id: str):
    """
    Reset a user's password.

    USER_ID should be the fully qualified (@username:domain.tld) user ID to reset the password of.
    """
    if not Confirm.ask("This will reset the user's password. Are you sure?"):
        return
    new_password = Prompt.ask("New password (blank for random): ", default="", password=True)
    if not new_password:
        new_password = secrets.token_hex(70)
        console.print("[yellow]Generated password: " + new_password)
    with console.status("Resetting password..."):
        http.reset_password(user_id, logout_devices=logout_devices, new_password=new_password)
    console.print("[green]Password reset.")


@main.command(name="reindex-events")
@click.pass_obj
def reindex_events(http: api.HTTPAPIManager):
    """
    Reindex all events.
    """
    http.reindex_events()
    console.print("[green]Events are now being re-indexed. This may take some time, so check your dendrite logs.")


@main.command(name="refresh-devices")
@click.argument("user_id")
@click.pass_obj
def refresh_devices(http: api.HTTPAPIManager, user_id: str):
    """
    Refresh a user's devices.

    USER_ID should be the fully qualified (@username:domain.tld) user ID to refresh the devices of.
    """
    with console.status("Refreshing devices..."):
        http.refresh_devices(user_id)
    console.print("[green]Devices refreshed.")


@main.command(name="purge-room")
@click.option("--i-am-sure", "skip_checks", is_flag=True, help="Skip the confirmation prompts. Not really recommended.")
@click.option(
    "--i-have-evacuated", "have_evacuated", is_flag=True, help="Skip the evacuation check. Not really recommended."
)
@click.argument("room_id")
@click.pass_obj
def purge_room(http: api.HTTPAPIManager, skip_checks: bool, have_evacuated: bool, room_id: str):
    """
    Purge a room. Removes all events from the room.

    WARNING: This is irreversible. Make sure you evacuated the room first.

    ROOM_ID should be the room ID to purge.
    """
    if not skip_checks:
        if not Confirm.ask("This will remove all events from the room. Are you sure?"):
            return
        if not Confirm.ask("Are you really sure?"):
            return
    if not have_evacuated:
        if not Confirm.ask("Have you already evacuated the room (dendrite-cli evacuate room)?"):
            if Confirm.ask("Would you like to?"):
                if not room(room_id):
                    return
            else:
                console.print("[yellow]Aborting.")
                return
    with console.status("Purging room..."):
        http.purge_room(room_id)
    console.print("[green]Purged room.")


@main.command(name="register")
@click.argument("shared_secret")
@click.argument("username")
@click.option("--display-name", "-d", default=None, help="Display name to use. Defaults to Username.")
@click.option("--admin", is_flag=True, help="Register as an admin user.")
@click.pass_obj
def register(http: api.HTTPAPIManager, shared_secret: str, username: str, display_name: str | None, admin: bool):
    """
    Register a new user.

    SHARED_SECRET should be the shared secret from the registration.yaml file.
    USERNAME should be the username to register.
    """
    password = Prompt.ask("Password: ", password=True)
    if display_name is None:
        display_name = username
    with console.status("Registering user..."):
        nonce = http.register()
        response = http.register(
            nonce,
            shared_secret=shared_secret,
            username=username,
            password=password,
            displayname=display_name,
            admin=admin,
        )
    console.print(f"[green]Registered %s (%s)" % (username, response["user_id"]))
    console.print(response)


@main.command()
@click.argument("user_id")
@click.pass_obj
def whois(http: api.HTTPAPIManager, user_id: str):
    """
    Get information about a user.

    USER_ID should be the fully qualified (@username:domain.tld) user ID to fetch the information of.
    """
    with console.status("Fetching user information..."):
        _user = http.whois(user_id)
    console.print(_user)
