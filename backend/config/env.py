"""Typed environment configuration, validated once at startup.

The only module that reads the environment. Everything else receives values from
`config.settings` or from the `env` object built here.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import PositiveFloat, PositiveInt, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/config/env.py -> repo root, independent of the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    django_secret_key: str
    django_debug: bool = False
    django_allowed_hosts: Annotated[list[str], NoDecode] = []

    # AD-13 (D13): the origins allowed to make a cross-origin request to the API. The
    # frontend's own origin is here because the browser calls the frontend, which proxies
    # to this API; Django's CSRF origin check compares `Origin` with its own host.
    csrf_trusted_origins: Annotated[list[str], NoDecode] = []

    # The frontend's base URL. The reset link points at the frontend's route, not at the
    # API, because the frontend is a different origin from this runtime.
    frontend_base_url: str = "http://localhost:3000"

    # The frontend's revalidation endpoint — the URL the backend POSTs a cache instruction
    # to when an event's public page has gone stale (FR-26, FR-27).
    #
    # **This is not `NEXT_PUBLIC_`-prefixed, and it is not the browser's URL.** The call is
    # server-to-server: the backend dials the frontend, so it needs the *server's* address
    # for the frontend, which in a deployed environment is not the public one.
    frontend_revalidation_url: str = "http://localhost:3000/revalidate"

    # The shared secret that authenticates the revalidation call (FR-26, FR-27).
    #
    # **It is separate from `CALENDAR_CREDENTIAL_KEY` on purpose, for three reasons.**
    # The credential key is protected by the `credential-key` import contract, so the
    # backend may not read it at all; AD-18 has it encrypted at rest, so it cannot be
    # compared in plaintext at request time; and it is a *different credential* — one key
    # per capability, so a single leaked key cannot both decrypt stored calendar
    # credentials and force page rebuilds.
    #
    # Required, with no default and no fallback, exactly like `calendar_credential_key`. A
    # missing value aborts the boot rather than leaving an app that boots healthy and
    # fails later, when an event changes.
    revalidation_secret: str

    # FR-48 billing. Required, with no default and no fallback, for the same reason as
    # `revalidation_secret` above: a missing key must abort the boot rather than leave an
    # app that looks healthy and fails the first time someone tries to pay.
    #
    # The webhook secret is **separate from the API key on purpose**. The API key authorises
    # calls out to Stripe; the webhook secret verifies calls in. One leaking does not give an
    # attacker the other's power, and Stripe rotates them independently.
    stripe_api_key: str
    stripe_webhook_secret: str
    # The provider's price identifiers, one per plan. Not secrets, but configuration: they
    # differ between test mode and live mode, so they cannot be literals in the adapter.
    stripe_price_monthly: str = ""
    stripe_price_yearly: str = ""

    # FR-48: the paths the checkout success and cancel URLs point at, and the path the
    # customer portal returns to. These are **configuration, not request input**, and they
    # are the whole reason the endpoints cannot be turned into an open redirect: the URLs
    # handed to the provider are built from `frontend_base_url` plus one of these paths.
    #
    # They are configurable rather than hardcoded for the same reason `frontend_base_url`
    # is: the frontend's routes can move without a backend change, and a deployment can
    # point the flow at a different host. What stays fixed is the rule — **the client never
    # supplies any part of these URLs**.
    # **They point at `/settings/account`, which is the screen that renders the plan.**
    # They pointed at `/settings/billing` until 2026-11-13, and that route has never
    # existed — so every completed checkout and every return from the customer portal
    # landed the user on a 404 immediately after paying. The plan, the portal button and
    # the `past_due` banner are all on `/settings/account`; that is where the flow
    # belongs, and the account screen ignores the query parameter it arrives with.
    billing_success_path: str = "/settings/account?checkout=complete"
    billing_cancel_path: str = "/settings/account?checkout=cancelled"
    billing_portal_return_path: str = "/settings/account"

    # How long the backend waits for the frontend's revalidation route handler to answer.
    revalidation_timeout_seconds: PositiveFloat = 5.0

    # FR-25: the Voyage API key for the real embedding adapter.
    #
    # **Required with no default and no fallback, exactly like `stripe_api_key`.** A
    # missing key must abort the boot rather than leave an app that looks healthy and
    # fails the first time an event needs embedding — and a silent zero cost would be
    # worse: the cost row would say the embedding was free.
    #
    # It is read here, in `config`, and never in `adapters`: the `layers` contract puts
    # `config` above `adapters`, so this is the only place the environment is read.
    voyage_api_key: str

    # How long the backend waits for Voyage to answer an embedding call.
    voyage_timeout_seconds: PositiveFloat = 30.0

    # Whether the caller's IP may be read from the `X-Forwarded-For` header.
    #
    # The header is **attacker-controlled** unless something in front of this runtime
    # overwrites it. Next's `NextResponse.rewrite` forwards the browser's headers as they
    # arrived and only *adds* `x-forwarded-host`, so a browser that sets
    # `X-Forwarded-For` has that value reach Django unchanged. Trusting it unconditionally
    # let any caller mint a fresh throttle bucket per request by varying the header, which
    # defeated the per-IP limit entirely.
    #
    # So it is off by default, and the per-IP throttle falls back to the socket address —
    # every caller through the proxy shares one bucket, which is coarse but cannot be
    # spoofed. Turning it on is only correct when a trusted edge overwrites the header
    # with the real client address (a load balancer in `proxy_set_header` mode, or the
    # Next proxy itself rewriting it).
    trust_forwarded_for: bool = False

    # runtime: the app connects as the DML-only roles. owner: migrations and tests (DDL).
    django_db_role: Literal["runtime", "owner"] = "runtime"

    # Required only for the owner role, so a runtime environment never holds DDL credentials.
    database_url_owner: str | None = None
    database_url_catalog: str
    database_url_personal: str

    redis_url: str
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025

    # AD-18: the application-level key the calendar credential is encrypted with. It is
    # **separate from DJANGO_SECRET_KEY** on purpose: SECRET_KEY signs sessions and is
    # frequently shared across environments, so using it to encrypt data at rest would
    # mean one leaked key decrypts every credential.
    #
    # Required, with no default and no fallback. A missing or malformed value aborts the
    # boot (settings are loaded at startup), rather than leaving an app that boots healthy
    # and fails later, when a user connects a calendar.
    calendar_credential_key: str

    adapter_mode: Literal["fake", "real"] = "fake"

    # Source fetches (ports.fetch). SOURCE_FETCH overrides ADAPTER_MODE for this one port, so
    # local dev can fetch real feeds while every other adapter stays fake. Unset: follow the mode.
    source_fetch: Literal["fake", "http"] | None = None

    # The throttle's counter store (ports.throttle). THROTTLE_ADAPTER overrides ADAPTER_MODE
    # for this one port. Unset: follow the mode.
    #
    # **This port is the one that cannot be faked locally, and the reason is that it
    # holds state the whole stack shares.** Every other port's fake is a stateless
    # stand-in — a canned LLM reply, a recorded crawl, a fake invoice — so a fake costs
    # the local stack nothing. The throttle is different: its counters are the product's
    # rate limits and the save cap, and they are read by the API, spent by the API and
    # cleared by the seed command, which are three *separate processes*. An in-process
    # store gives each of them its own copy, so the seed's `reset_save_allowance` clears
    # the seed's counters and not the API's — and a repeatable seed stops being
    # repeatable, because the second run finds the cap already spent.
    #
    # **So the local stack uses the real Redis adapter**, and only the counter's storage
    # changes: Redis is already in the stack (it is the Celery broker), the key layout is
    # the same one production uses, and the rate limits themselves are untouched. The
    # in-memory adapter stays the unit tests' tool, because a test pins the clock and
    # wants an isolated counter — neither of which Redis could give it.
    #
    # `memory` is offered so a developer can still run without Redis, at the cost of the
    # cross-process sharing described above.
    throttle_adapter: Literal["memory", "redis"] | None = None

    # The object store (ports.blob). BLOB_ADAPTER overrides ADAPTER_MODE for this one port.
    # Unset: follow the mode — which means the S3 adapter pointed at the local MinIO, the
    # same arrangement email has with Mailpit. `memory` runs with no object store at all.
    blob_adapter: Literal["memory", "s3"] | None = None

    # --- The object store (ports.blob) ---
    #
    # **Two endpoints, because they are two different addresses for one service.** The API
    # dials the store from inside the compose network, where it answers to a service name;
    # the browser fetches a presigned URL from outside it, where it answers to 127.0.0.1.
    # A SigV4 signature is bound to the host it was minted for, so a URL signed for the
    # internal name cannot be fetched by a browser — and that failure appears *only* in a
    # browser, never in a backend test. In a deployment where the store has one address,
    # both of these carry it.
    blob_endpoint: str = ""
    blob_public_endpoint: str = ""
    blob_region: str = "us-east-1"
    blob_bucket: str = ""
    # Local-only values in .env.example; production reads them from the platform secret
    # store, like every other credential here.
    blob_access_key: str = ""
    blob_secret_key: str = ""
    # How long a presigned URL is good for. It is the *inside* of a stable app-owned URL,
    # not something rendered into a page, so it is short: long enough to survive a
    # redirect and the fetch that follows, not long enough to be worth passing around.
    blob_url_ttl_seconds: PositiveInt = 300

    # The calendar port (ports.calendar). CALENDAR_ADAPTER overrides ADAPTER_MODE for this one
    # port, so a local run can import a *real* calendar while every other adapter stays fake.
    # Unset: follow the mode — which means `fake`, and the fake returns two fixed events for
    # every address it is given.
    #
    # **Why this override exists.** `ADAPTER_MODE=real` does not boot yet (there is no real
    # `llm` or `email` adapter), so without a per-port override there was no way to point a
    # local stack at a genuine ICS feed at all. A developer who connected their own Google
    # calendar got the fake's "Team stand-up" and "Dinner" back, with a healthy connection and
    # no error anywhere to explain it — the stand-in is indistinguishable from a working
    # import until you read the uids.
    #
    # It names the *adapter*, not the mode, exactly as SOURCE_FETCH and THROTTLE_ADAPTER do.
    calendar_adapter: Literal["fake", "ics"] | None = None
    source_fetch_user_agent: str = (
        "EventPulse24-SourceFetcher/0.1 (+https://github.com/JobaerAhamed-23/EventPulse24)"
    )
    source_fetch_max_bytes: PositiveInt = 10 * 1024 * 1024
    source_fetch_dns_timeout: PositiveFloat = 3.0
    source_fetch_connect_timeout: PositiveFloat = 5.0
    source_fetch_read_timeout: PositiveFloat = 15.0
    source_fetch_write_timeout: PositiveFloat = 5.0
    source_fetch_total_timeout: PositiveFloat = 30.0
    source_fetch_max_redirects: int = 5
    source_fetch_allowed_ports: Annotated[list[int], NoDecode] = [80, 443]
    # The fake fetch adapter's fixtures (index.json + files). Not needed when fetching over http.
    source_fixtures_dir: Path = REPO_ROOT / "backend" / "tests" / "fixtures" / "sources"

    # FR-2: the city the **fake** geo adapter reports. The fake is the local and CI default
    # (ADAPTER_MODE=fake), and the work item asks for it to be "configurable to return a
    # chosen city" — so this is where the chosen city comes from.
    #
    # Unset or empty: the fake reports **no location**, which is the geo-miss branch. Set it
    # to a supported city and every request resolves to that city; set it to an unsupported
    # one and the endpoint takes the fallback branch.
    #
    # This is the *fake's* configuration, so it has no effect when ADAPTER_MODE=real.
    geo_fake_city: str | None = None

    @field_validator("django_allowed_hosts", "csrf_trusted_origins", mode="before")
    @classmethod
    def split_comma_separated(cls, value: object) -> object:
        # Env values arrive as "a,b,c"; NoDecode stops pydantic-settings parsing them as JSON.
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value

    @field_validator("source_fetch_allowed_ports", mode="before")
    @classmethod
    def split_ports(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(port) for port in value.split(",") if port.strip()]
        return value

    @field_validator("source_fetch_allowed_ports")
    @classmethod
    def ports_in_range(cls, value: list[int]) -> list[int]:
        if not value or any(not 1 <= port <= 65535 for port in value):
            raise ValueError("SOURCE_FETCH_ALLOWED_PORTS must be ports in 1..65535")
        return value

    @field_validator("source_fetch_max_redirects")
    @classmethod
    def redirects_not_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("SOURCE_FETCH_MAX_REDIRECTS must be 0 or more")
        return value

    @model_validator(mode="after")
    def real_calendars_need_a_real_fetch(self) -> "Settings":
        """`CALENDAR_ADAPTER=ics` is meaningless while the fetch port is fake.

        **The ICS adapter never opens a socket.** It resolves `SourceFetchPort` from the
        registry and calls `fetch()`, so the hardened client does the SSRF policy, the size
        limits and the deadline — one implementation, not a second weaker copy. The
        consequence is that pointing the calendar port at the real adapter while the fetch
        port is still fake buys nothing: the canned fetch answers, and the developer gets
        stand-in data from a configuration that says `ics` on the tin.

        That is precisely the failure this override was added to end, so it is refused at
        boot with the variable to set, rather than discovered later by reading event uids.
        """
        if self.calendar_adapter != "ics":
            return self
        fetch = self.source_fetch or ("http" if self.adapter_mode == "real" else "fake")
        if fetch != "http":
            raise ValueError(
                "CALENDAR_ADAPTER=ics needs a real fetch: set SOURCE_FETCH=http. "
                "The ICS adapter fetches through the shared source-fetch port, so a fake "
                "one would return stand-in data for every calendar address."
            )
        return self

    @model_validator(mode="after")
    def s3_blobs_need_a_configured_bucket(self) -> "Settings":
        """**The S3 adapter cannot be chosen without somewhere to put bytes.**

        The same shape as `real_calendars_need_a_real_fetch`: the setting that *selects*
        a real integration is validated against the settings that *configure* it, once,
        at startup — rather than booting a stack that looks healthy and fails the first
        time a user uploads a picture.

        **The memory adapter needs none of this**, which is why these have defaults and
        the check is conditional: a developer running `BLOB_ADAPTER=memory`, and the whole
        test suite, must not be made to carry credentials for a store they never dial.

        **It fires only when `BLOB_ADAPTER=s3` was asked for by name.** The *resolved*
        adapter table is checked separately, by `config.checks.check_blob_storage`, and
        that split is load-bearing rather than tidy: this validator runs while `env` is
        being built, which happens before any settings module — including
        `config/settings_test.py` — has had a chance to say which adapter it wants. A
        validator that refused the unset case here would refuse to **boot the test
        suite**, which runs on the in-memory adapter and dials no store at all.
        """
        if self.blob_adapter != "s3":
            return self
        missing = [
            name
            for name, value in (
                ("BLOB_ENDPOINT", self.blob_endpoint),
                ("BLOB_PUBLIC_ENDPOINT", self.blob_public_endpoint),
                ("BLOB_BUCKET", self.blob_bucket),
                ("BLOB_ACCESS_KEY", self.blob_access_key),
                ("BLOB_SECRET_KEY", self.blob_secret_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "BLOB_ADAPTER=s3 needs " + ", ".join(missing) + ". "
                "Set them in .env (make env), or set BLOB_ADAPTER=memory to run with no "
                "object store."
            )
        return self

    @model_validator(mode="after")
    def owner_role_requires_owner_url(self) -> "Settings":
        if self.django_db_role == "owner" and not self.database_url_owner:
            raise ValueError("DATABASE_URL_OWNER is required when DJANGO_DB_ROLE=owner")
        return self

    @field_validator("calendar_credential_key")
    @classmethod
    def credential_key_is_well_formed(cls, value: str) -> str:
        """The key must parse, and it must be the application-level key.

        Validated here, at settings-load time, so a malformed key aborts the boot with a
        message naming the variable. The parser itself lives in `shared.credential_key`,
        which is stdlib-only, so there is exactly one definition of the format — the
        system check and this validator cannot disagree — and `config` never reaches the
        cipher (the `crypto-library` import contract).
        """
        from shared.credential_key import InvalidCredentialKey, parse_key

        try:
            parse_key(value)
        except InvalidCredentialKey as exc:
            raise ValueError(str(exc)) from exc
        return value


env = Settings()
