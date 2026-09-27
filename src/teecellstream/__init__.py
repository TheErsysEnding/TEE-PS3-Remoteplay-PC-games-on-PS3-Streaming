"""TEE Cell Stream Server Linux - streams the desktop to a PS3 running the cell-stream homebrew app.

Linux port of cell-stream-server (ps3-dev, Apache-2.0, release 174-a5dd795).
"""

# ".t" and three digits mark a build still under test (1.0.1.t001, .t002, ...); only one that passed its
# test gets a plain number. The PS3 app follows the same scheme (ps3-src/.../include/app-version.h).
__version__ = "1.1.0"
# The DEBIAN version carries an epoch. Development ran to 1.38.0 before the first public release was
# cut at 1.0.0, and dpkg compares versions strictly: without the epoch apt sees 1.0.0 as older than
# what is installed and refuses to "upgrade" to it. "1:" is exactly the mechanism Debian provides for
# a version number that has been restarted, and it stays on every version from here on.
DEB_EPOCH = "1"
UPSTREAM_VERSION = "174-a5dd795"

APP_ID = "de.tee.CellStreamServer"
APP_NAME = "TEE Cell Stream Server"
APP_EXEC = "tee-cell-stream-server"

# ------------------------------------------------------------------ where to find the author
#
# One place for all three, because they appear in six: the Linux window, the Qt window, both About
# boxes, the PS3 app's waiting screen and controls list, the package artwork, the README and the
# Windows installer. A link written out a second time is a link that goes stale in one of them.
#
# The donation link is not decoration: it pays for the server this project is developed and hosted
# on, and the amount that does it is one euro a month. It is worth saying so plainly rather than
# putting up a coy "support me" - people give when they know what it buys.
LINK_HUB = "linktr.ee/theersysending"
LINK_DONATE = "bero-host.de/spenden/x8atfjdyolqr"
LINK_GITHUB = "github.com/TheErsysEnding/TEE-PS3-Remoteplay-PC-games-on-PS3-Streaming"
URL_HUB = "https://" + LINK_HUB
URL_DONATE = "https://" + LINK_DONATE
URL_GITHUB = "https://" + LINK_GITHUB
URL_RELEASES = URL_GITHUB + "/releases/latest"

DONATE_HEADLINE = "Keep the server running"
DONATE_PITCH = ("One euro pays for a whole month of the server this project lives on. "
                "PayPal, paysafecard, bank transfer or crypto.")
DONATE_PITCH_SHORT = "1 € pays for a month of the project's server"
