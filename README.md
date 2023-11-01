# Dendritecli
A friendly command line interface for managing Dendrite admin APIs.

## Installing
You will need python 3.10 or later. You will also need `pipx` (`pip install pipx && python3 -m pipx ensurepath`)

You can then install dendritecli with the following command:
```shell
pipx install git+https://github.com/nexy7574/dendritecli.git
```

or, as a library:
```shell
pip install git+https://github.com/nexy7574/dendritecli.git
```

## Usage
### As a command line tool
`pipx` creates two commands (in `$HOME/.local/bin` on Linux): `dendritecli` and `dendrite-cli`. 
They are identical, so you can use either one.

You can get help with `dendritecli --help` or `dendritecli <command> --help`.

The [Configuration File](#configuration-file) section describes how to configure dendritecli.

### As a library
You can use dendritecli as a library. The main entry point is `dendritecli.api.HTTPAPIManager`.

```python
from dendritecli.api import HTTPAPIManager

manager = HTTPAPIManager(
    access_token="<access token>"
)
```

## Configuration File
You can configure dendritecli with a configuration file. The default location is `$HOME/.config/dendritecli.toml`,
or if `$HOME/.config` does not exist, `$HOME/.dendritecli.toml`.

The configuration file supports the following options:
```toml
access_token = "<the access token from your homeserver>"
server = "<the URL of your homeserver>"  # e.g: matrix-client.matrix.org, not matrix.org

override-password-length-check = false
# Due to a bug in Dendrite (https://github.com/matrix-org/dendrite/issues/3012), passwords cannot be over 72 bytes
# in length (usually). If you want to override this check, set this to true.
# You shouldn't do this unless you know your homeserver 

timeout = 60.0
# the timeout for requests, in seconds. Includes connect, read, and write timeouts.
# By default, the library has a 10 second connect timeout, 3 minute read timeout (for long responses), 
# and a 1 minute write timeout. This has been specially tuned for Dendrite servers.
# If you're having issues with timeouts (due to a slow homeserver), feel free to bump this to a higher value,
# like 600 (10 minutes).

[proxies]
# By default, if these arent specified, the library will use the system proxy settings.
http = "http://my.http.prox:13"
https = "https://my.https.prox:13"
socks5 = "socks5://my.socks5.prox:13"

[headers]
# headers to send with every request
# You should not overwrite Accept, or Content-Type, as they are required for the API to work.
# You also cannot overwrite User-Agent.
X-My-Header = "my header value"
```
