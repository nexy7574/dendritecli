# Dendritecli

[![Python package](https://github.com/nexy7574/dendritecli/actions/workflows/python-package.yml/badge.svg)](https://github.com/nexy7574/dendritecli/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/dendritecli.svg)](https://badge.fury.io/py/dendritecli)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/dendritecli)](https://pypi.org/project/dendritecli/)

A friendly command line interface for managing Dendrite admin APIs.

## Features

Dendritecli has full support for all the [admin endpoints](https://matrix-org.github.io/dendrite/administration/adminapi),
including:

* Registering users (the same as the create-account command)
* Evacuating both rooms and users
* Puring rooms
* Refreshing devices
* Reindexing events
* `whois`

with the addition of some patches and workarounds for missing things, such as:

* Listing registered accounts
* Listing rooms
* Deactivating accounts

### As a library

Dendritecli also supports being used as a library, with a simple API.

If you wanted to do something with a web interface, for example, you could do the following:

```python
...
import json
from dendritecli.api import HTTPAPIManager as DendriteManager


def evacuate_user(user: str):
    manager = DendriteManager("access_token")
    # ^ defaults to http://localhost:8008.
    affected_rooms = manager.evacuate_user(user)
    return json.dumps(affected_rooms)
```

## Installing

You will need python 3.10 or later. You will also need `pipx` (`pip install pipx && python3 -m pipx ensurepath`)

You can then install dendritecli with the following command:

```shell
#pipx install git+https://github.com/nexy7574/dendritecli.git
# We're on PyPi now:
pipx install dendritecli
# Or, if you want to be able to use it as a library:
pip install dendritecli
```

## Usage

### As a command line tool

`pipx` creates two commands (in `$HOME/.local/bin` on Linux): `dendritecli` and `dendrite-cli`. 
They are identical, so you can use either one.

You can get help with `dendritecli --help` or `dendritecli <command> --help`.

The [Configuration File](#configuration-file) section describes how to configure dendritecli.


## Configuration File

You can configure dendritecli with a configuration file. The default location is `$HOME/.config/dendritecli.toml`,
or if `$HOME/.config` does not exist, `$HOME/.dendritecli.toml`.

The configuration file supports the following options:

```toml
access_token = "<the access token from your homeserver>"
server = "<the URL of your homeserver>"  # e.g: matrix-client.matrix.org, not matrix.org
database_uri = "<the URI of your database>"  
# e.g: sqlite:///dendritecli.db
# e.g: postgres://username:password@hostname:port/database?option=value
# Both SQLite and PostgreSQL are supported.

override-password-length-check = false
# Due to a bug in Dendrite (https://github.com/matrix-org/dendrite/issues/3012), passwords cannot be over 72 bytes
# in length (usually). If you want to override this check, set this to true.
# You shouldn't do this unless you know your homeserver 

timeout = 120.0
# the timeout for requests, in seconds. Includes connect, read, and write timeouts.
# By default, the library has a 10 second connect timeout, 3 minute read timeout (for long responses), 
# and a 1 minute write timeout. This has been specially tuned for Dendrite servers.
# If you're having issues with timeouts (due to a slow homeserver), feel free to bump this to a higher value,
# like 600 (10 minutes).

[proxies]
# By default, if these arent specified, the library will use the system proxy settings.
http = "http://my.http.proxy:13"
https = "https://my.https.proxy:13"
socks5 = "socks5://my.socks5.proxy:13"

[headers]
# headers to send with every request
# You should not overwrite Accept, or Content-Type, as they are required for the API to work.
# You also cannot overwrite User-Agent.
X-My-Header = "my header value"
```
