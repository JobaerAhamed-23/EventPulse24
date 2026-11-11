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

    # How long the backend waits for the frontend's revalidation route handler to answer.
    revalidation_timeout_seconds: PositiveFloat = 5.0

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
