import functools
import logging
import sqlite3
import typing
from pathlib import Path

import psycopg
from urllib.parse import urlparse, parse_qs


__all__ = (
    "SQLHandler",
)


class SQLHandler:
    def __init__(self, uri: str):
        url = urlparse(uri)
        if url.scheme.lower() not in ("postgres", "postgresql", "sqlite", "sqlite3"):
            raise ValueError("Invalid URI scheme (not of postgres:// or sqlite3://)")
        if len(url.path) <= 1:
            raise ValueError("Invalid URI path (no database name)")

        self.username = url.username or None
        self.password = url.password or None
        self.host = url.hostname or None
        self.port = url.port or 5432
        self.database = url.path[1:]

        if url.query:
            query = parse_qs(url.query)
            self.sslmode = query.get("sslmode", ["prefer"])[0]
        else:
            self.sslmode = "prefer"
        if url.scheme.lower() in ("sqlite", "sqlite3"):
            path = Path(url.path).absolute()
            if not path.exists():
                raise FileNotFoundError(f"Database file {path} does not exist.")
            self.driver = functools.partial(sqlite3.connect, str(path))
        else:
            self.driver = self._psycopg_connect()

        self.connection: typing.Optional[typing.Union[psycopg.Connection, sqlite3.Connection]] = None
        self.log = logging.getLogger("dendritecli.sql")

    def __enter__(self) -> "SQLHandler":
        self.log.info("Connecting to database.")
        self.connection = self.driver()
        self.log.debug("Connection to database established.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            self.log.info("Closing database connection")
            self.connection.close()
            self.log.debug("Database connection closed")
        self.connection = None
        self.log.debug("Database connection destroyed.")

    def _psycopg_connect(self):
        return functools.partial(
            psycopg.connect,
            user=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            dbname=self.database,
            sslmode=self.sslmode,
        )

    def list_accounts(self) -> typing.Generator[dict[str, str | int | None], None, None]:
        """
        Lists all accounts registered in the database.

        This function is a generator.
        """
        with self as instance:
            with instance.connection.cursor() as cursor:
                self.log.info("Querying userapi_accounts and userapi_profiles tables.")
                cursor.execute(
                    """
                    SELECT 
                      userapi_accounts.localpart,
                      userapi_accounts.server_name,
                      created_ts,
                      appservice_id,
                      is_deactivated,
                      account_type,
                      display_name,
                      avatar_url
                    FROM userapi_accounts
                    INNER JOIN userapi_profiles
                    ON userapi_accounts.localpart = userapi_profiles.localpart;
                    """
                )
                for row in cursor:
                    self.log.debug("Yielding row %r", row)
                    yield {
                        "localpart": row[0],
                        "server_name": row[1],
                        "created_ts": row[2],
                        "appservice_id": row[3],
                        "is_deactivated": row[4],
                        "account_type": row[5],
                        "display_name": row[6],
                        "avatar_url": row[7],
                    }

    def list_rooms(self) -> typing.Generator[dict[str, str | int | None], None, None]:
        """
        Lists all rooms registered in the database.

        Also fetches and known room aliases.
        """
        with self as instance:
            with instance.connection.cursor() as cursor:
                self.log.info("Querying roomserver_room_aliases and roomserver_rooms tables via left join.")
                cursor.execute(
                    """
                    SELECT 
                      roomserver_room_aliases.alias,
                      roomserver_rooms.room_id,
                      roomserver_rooms.room_version
                    FROM roomserver_rooms
                    LEFT JOIN roomserver_room_aliases
                    ON roomserver_room_aliases.room_id = roomserver_rooms.room_id;
                    """
                )
                for row in cursor:
                    self.log.debug("Yielding row %r", row)
                    yield {
                        "alias": row[0],
                        "room_id": row[1],
                        "room_version": row[2],
                    }
