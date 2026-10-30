"""A local ICS server for the calendar tests: switchable, and it records what it was asked.

**Where it lives.** It sits at the top of the `tests` package, beside `tests/csrf.py`,
because more than one package needs it: the end-to-end proof drives the whole
onboarding-and-calendar flow through it, and the adapter's own tests need a *real*
socket to prove that a credential fetch writes no URL into httpx's logger. A server
mocked at the transport level would never reach that logger, so the test would pass
for the wrong reason. One server, two consumers.

**Why a server at all.** The proof has to exercise the *whole* path — the fetch, the
conditional request, the revocation, the log — against a real socket, because the parts
being proven (the SSRF guard at connect time, the credential redaction in the logs, the
`304`/`410` handling) only exist on that path. A mock would prove nothing about any of
them.

**Why a server rather than a live provider.** A live Google or iCloud account in CI would
be slow, flaky, would need credentials, and would make the proof's outcome depend on
someone's inbox. This server is deterministic: same feed, same headers, same statuses,
every run.

**What it serves.** The body is `tests/fixtures/calendars/google.ics`, read from disk —
not embedded in this file — so the fixture stays the single source of truth for what the
feed contains.

**How it is switchable.** A `status` attribute decides what the next request is answered
with: `200` (the feed), `304` (not modified, honouring the request's validators), or
`410` (gone — the revocation). The switch is what lets one scenario walk the whole
lifecycle of a calendar connection: connect, poll, poll again unchanged, then revoked.

**Why it records requests.** A `requests` list of `RecordedRequest`s lets the test assert
that the poll *actually asked* — a conditional header was sent, the second poll carried
`If-None-Match`, the third was answered 410. Without the log, "the connection became
`needs_reconnect`" would only prove that something failed, not that it failed for the
right reason.

**Why it speaks TLS.** The calendar adapter refuses `http://` — rightly: the ICS address
*is* the credential (AD-18), and fetching it over cleartext would carry the secret in the
open on every poll. The adapter accepts `https://` and rewrites `webcal://` to it, so
there is no scheme that reaches the fixture server without TLS. The server therefore
wraps its socket in TLS with a **self-signed certificate generated at runtime** for
`127.0.0.1`.

The certificate is generated per run rather than committed, so no test artefact has to
be kept alive or rotated, and the expiry is always in the future. The client trusts it
through an explicitly supplied SSL context — **verification stays on**: the proof adds a
trust anchor, it does not turn checking off. The adapter's default trust store is
untouched, and nothing in the production path is changed.

**Why it is a plain `ThreadingHTTPServer`.** It runs on a daemon thread inside the test
process, so it starts and stops with the test and there is no leftover process to clean
up. It binds to `127.0.0.1:0` — an ephemeral port, so parallel test runs cannot collide
— and the port is read back from the socket, never guessed.
"""

import datetime
import ssl
import tempfile
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

#: The feed the server serves. Read from disk so the fixture file stays the single
#: source of truth for the calendar's contents.
FIXTURE_ICS = Path(__file__).resolve().parent / "fixtures" / "calendars" / "google.ics"

#: The ETag the server hands out. A fixed value, so a test can assert the connection
#: stored exactly this validator.
ETAG = '"fixture-v1"'

#: The Last-Modified the server hands out.
LAST_MODIFIED = "Wed, 12 Nov 2026 18:00:00 GMT"

#: The status codes the server can be switched to.
STATUS_OK = 200
STATUS_NOT_MODIFIED = 304
STATUS_GONE = 410


@dataclass(frozen=True)
class RecordedRequest:
    """One request the server was asked for."""

    method: str
    path: str
    if_none_match: str | None
    if_modified_since: str | None
    user_agent: str | None
    cookie: str | None

    @property
    def is_conditional(self) -> bool:
        """Whether the request carried a cache validator."""
        return bool(self.if_none_match or self.if_modified_since)


def _self_signed_cert(directory: Path) -> tuple[Path, Path]:
    """A self-signed certificate for `127.0.0.1`, written into `directory`.

    The `SubjectAlternativeName` carries the **IP address**, not a hostname: the proof
    connects to `127.0.0.1`, and a certificate with only a DNS name would fail the
    hostname check against an IP literal.

    The key is generated per run and never leaves the test's temporary directory.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path = directory / "fixture-cert.pem"
    key_path = directory / "fixture-key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@dataclass
class FixtureIcsServer:
    """A switchable ICS server on loopback.

    **Used as a context manager**, so the server is always shut down — even if the test
    fails midway:

    ```python
    with FixtureIcsServer() as server:
        url = server.url("/feed.ics")
    ```
    """

    #: What the next request is answered with. Change it between steps.
    status: int = STATUS_OK

    #: The body served on a 200. Defaults to the fixture file's contents.
    body: bytes = b""

    #: Every request the server was asked for, in order.
    requests: list[RecordedRequest] = field(default_factory=list)

    _server: ThreadingHTTPServer | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _cert_path: Path | None = field(default=None, init=False, repr=False)
    _key_path: Path | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.body:
            self.body = FIXTURE_ICS.read_bytes()

    # --- The lifecycle ------------------------------------------------------------------------

    def start(self) -> "FixtureIcsServer":
        """Bind, serve on a daemon thread, and return self."""
        directory = Path(tempfile.mkdtemp(prefix="ep-fixture-ics-"))
        self._cert_path, self._key_path = _self_signed_cert(directory)

        server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        # `daemon_threads` so a lingering keep-alive connection cannot keep the process
        # alive after the test finishes.
        server.daemon_threads = True

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self._cert_path), str(self._key_path))
        server.socket = context.wrap_socket(server.socket, server_side=True)

        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="fixture-ics", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """Shut the server down and release the port."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "FixtureIcsServer":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    # --- The address --------------------------------------------------------------------------

    @property
    def port(self) -> int:
        """The ephemeral port the server was given."""
        if self._server is None:
            raise RuntimeError("the server is not running")
        return self._server.server_address[1]

    @property
    def certificate_path(self) -> Path:
        """The self-signed certificate the client must trust."""
        if self._cert_path is None:
            raise RuntimeError("the server is not running")
        return self._cert_path

    def ssl_context(self):
        """A client SSL context that trusts the fixture certificate.

        **Verification stays on.** The context is httpx's own default trust store with
        the fixture's certificate *added*, so the peer is still verified and the hostname
        is still checked — the proof adds a trust anchor, it does not disable checking.
        """
        import httpx

        context = httpx.create_ssl_context(trust_env=False)
        context.load_verify_locations(str(self.certificate_path))
        return context

    def url(self, path: str = "/feed.ics") -> str:
        """The feed's URL. **This is the credential** — never log it, never echo it.

        The path is a *secret* too: a real provider's ICS address carries a token in it,
        which is exactly why the credential is encrypted at rest (AD-18). The proof
        therefore generates the URL at runtime and asserts that it never appears in the
        logs, the responses or the DOM.
        """
        return f"https://127.0.0.1:{self.port}{path}"

    # --- The switches -------------------------------------------------------------------------

    def serve_ok(self) -> None:
        """Answer 200 with the feed."""
        self.status = STATUS_OK

    def serve_not_modified(self) -> None:
        """Answer 304 — the feed has not changed since the client's validators."""
        self.status = STATUS_NOT_MODIFIED

    def serve_gone(self) -> None:
        """Answer 410 — the provider revoked the address."""
        self.status = STATUS_GONE

    def reset(self) -> None:
        """Forget every recorded request, and go back to answering 200."""
        self.requests.clear()
        self.status = STATUS_OK


def _make_handler(server: FixtureIcsServer):
    """The request handler, bound to one server instance.

    A class is built per server so the handler can reach the instance's switch and its
    request log without any global state.
    """

    class Handler(BaseHTTPRequestHandler):
        # The default handler logs every request to stderr, which would put the URL —
        # the credential — into the test output. AD-13 says the credential never reaches
        # a log, and a test's own stderr is a log.
        def log_message(self, format, *args):  # noqa: A002 - the stdlib's parameter name
            pass

        def do_GET(self):  # noqa: N802 - the stdlib's method name
            server.requests.append(
                RecordedRequest(
                    method=self.command,
                    path=self.path,
                    if_none_match=self.headers.get("If-None-Match"),
                    if_modified_since=self.headers.get("If-Modified-Since"),
                    user_agent=self.headers.get("User-Agent"),
                    cookie=self.headers.get("Cookie"),
                )
            )

            if server.status == STATUS_NOT_MODIFIED:
                # A 304 carries no body. The validators go back so the client can store
                # them, which is the state a real provider leaves behind.
                self.send_response(STATUS_NOT_MODIFIED)
                self.send_header("ETag", ETAG)
                self.send_header("Last-Modified", LAST_MODIFIED)
                self.end_headers()
                return

            if server.status == STATUS_GONE:
                # The revocation. A body would be noise; the status is the message.
                self.send_response(STATUS_GONE)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            self.send_response(STATUS_OK)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Length", str(len(server.body)))
            self.send_header("ETag", ETAG)
            self.send_header("Last-Modified", LAST_MODIFIED)
            self.end_headers()
            self.wfile.write(server.body)

    return Handler
