"""The auth endpoints' wire shapes (AD-19).

Request and response shapes are Pydantic schemas, never ad-hoc dicts. These live in the
`identity` app because the surface owns the contract; the data comes from
`apps.identity.services`, which owns the commands.

**Two of these shapes are deliberately informationless.** The sign-up and the
password-reset-request responses carry the same fields whether the address was known or
not, because an answer that differs between the two cases is an account-existence oracle
(AD-18). The fields below are the *whole* answer — there is no second shape to fall back
to, so the two cases cannot drift apart.

**`CurrentUserOut` carries no password field.** There is no field for the hash, no field
for the last-login stamp, and no `**kwargs` catch-all: the response is spelled out, so a
new column on `User` cannot leak by accident.
"""

from uuid import UUID

from ninja import Schema

from apps.personalization.schemas import OnboardingStatusOut
from ports.billing import ProPlan


class SignUpIn(Schema):
    """The sign-up request: an address, a password, and optionally a home city.

    The password is a plain string here and is never echoed back. It goes to
    `apps.identity.services.sign_up`, which validates it against Django's configured
    password validators and hashes it.

    **`city` is optional, and it is the visitor's preview choice carried across
    sign-up.** The preview choice lives in a **session cookie** read in the browser
    only — deliberately, because a server-side choice would make `/preview` vary per
    visitor and break AD-12's cacheability. So the carry is a **request field**: the
    frontend reads the cookie and sends the city here.

    A city in the curated catalog is stored **exactly as sent**, with `city_source`
    `choice`. A city **outside** it is **refused** — the account is still created, but
    the city is not stored and the caller is told which value was refused — because the
    stored city is the picked city, and a reader who chose Chittagong must not be
    answered with New York City. The sign-up **response** says nothing about the city
    either way — a city is not an account-existence oracle, but the response shape
    carries nothing beyond `status` in any case.
    """

    email: str
    password: str
    city: str | None = None


class SignUpOut(Schema):
    """The sign-up answer. The same for a new address and an existing one.

    There is no `created` flag, and no account id: either would say whether the address
    was taken. The account holder of an existing address is told by email instead.
    """

    status: str = "accepted"


class SignInIn(Schema):
    """The sign-in request: an address and a password."""

    email: str
    password: str


class SignInOut(Schema):
    """The sign-in answer. The same for a wrong password and an unknown address.

    The status is the only field. A body that named the account, or said which half of
    the pair was wrong, would be the enumeration leak the services are careful to avoid.
    """

    status: str = "signed_in"


class SignOutOut(Schema):
    """The sign-out answer. The session is over; nothing else is said."""

    status: str = "signed_out"


class CurrentUserOut(Schema):
    """The signed-in user.

    The id and the email are what the frontend needs. There is no password field, no
    permission field and no catch-all, so nothing internal can ride along.

    The **onboarding status** is here, and it is here because the frontend needs it to
    decide between the onboarding flow and the home. It says only whether the onboarding
    is finished and which step the user is on — it carries no interests and no digest
    preference, because `me` is about *who* the user is and a settings blob there would
    grow without bound. The full state lives at `/api/personal/onboarding`.

    The **name** is here for the same reason the email is: the frontend shows it on
    every screen, so it is a read the frontend already makes. It is `""` when no name is
    set — the one "no name set" state — and the frontend renders its own email-derived
    fallback in that case. **The backend does not guess a name from an address**: how a
    human renders their own name is a display concern, not a stored one.

    It is read through `personalization`'s **published interface** — the service, never
    the model — because `identity` may not reach into another app's tables (AD-2). The
    import contract `models-personalization` proves it.

    The **pending deletion** is here for the same reason `pending_email` is: the
    frontend has to be able to *say* that an account is scheduled for destruction, and
    it cannot say it from a boolean. A person who asked to delete their account and
    then changed their mind needs to reach the way back — and a way back that does not
    say when the account dies is not a way back, it is a countdown they cannot read.

    **The two moments ride every page's payload, and that is the cost.** `me` is read
    on every render, so two small strings are carried by every user forever, including
    the ones who will never delete anything. The alternative is a second round trip on
    one screen — and it cannot be the shell's job either, because the shell is not
    where the danger zone lives. **The trade is two strings on every payload, and it
    buys the ability to name the date.**
    """

    id: UUID
    email: str
    name: str
    #: Where to fetch this account's picture, or `""` when none is set.
    #:
    #: **It is here for the same reason `name` is**: the shell shows it on every page, so
    #: it rides the read the frontend already makes. A second endpoint for the same row
    #: would be a second round trip on every render.
    #:
    #: **A URL, not the key**, and an **app-owned** URL rather than a signed one. The
    #: bucket is private, and `object-storage-and-minio` measured that a presigned URL
    #: cannot be made stable without racing botocore's signing path — so a signature baked
    #: into this field would change on every render and defeat the browser cache. This URL
    #: is stable for as long as the picture is, and the signature is minted behind a
    #: redirect at `GET /api/auth/profile/avatar/{version}`.
    #:
    #: `""` when unset — not `null` and not absent — the one "no picture" state, matching
    #: `name` and `pending_email` above.
    avatar_url: str = ""
    #: The address an outstanding email change is *to*, or `""` when there is none.
    #:
    #: **The address, not a boolean**, and that was a decision rather than convenience.
    #: A boolean leaves the screen unable to say *which* address a link went to, which is
    #: precisely what someone who mistyped it needs to see before they wait a day for a
    #: mail that will never arrive. It costs putting the address in every page's payload
    #: — but it is **the account holder's own data about their own pending change**, and
    #: `me` is readable by nobody else.
    #:
    #: It is `""` and never `null`, for the same reason `name` is: "none pending" is one
    #: state, not two.
    pending_email: str = ""
    #: When that pending change's link stops working, ISO-8601, or `""` when none.
    #:
    #: **The moment, not the duration.** The screen has to tell someone whether it is
    #: still worth waiting for a mail, and a duration typed into the frontend would be
    #: the same mistake the mail templates had: a number that keeps saying "24 hours"
    #: after the constant says otherwise. The server knows when this link dies, so the
    #: server says when.
    pending_email_expires_at: str = ""
    #: When this account will be destroyed, ISO-8601, or `""` when no deletion is pending.
    #:
    #: **The moment, not the duration, and not a boolean.** The surface has to say *when*
    #: the account dies — that is the whole point of a grace period, and a person deciding
    #: whether to cancel needs a date rather than "soon". `"deletion_pending": true`
    #: cannot answer that, and a duration typed into the frontend would be the same
    #: mistake the mail templates had: a number that keeps saying "30 days" after the
    #: constant says otherwise.
    #:
    #: **The server computed this once, at request time**, and a later request cannot move
    #: it — so this is the promise the product made, carried verbatim.
    #:
    #: It is `""` and never `null`, for the same reason `name` is: "none pending" is one
    #: state, not two.
    deletion_scheduled_for: str = ""
    #: When the deletion was requested, ISO-8601, or `""` when none is pending.
    #:
    #: **This is what lets the surface say "you asked on the 3rd".** It differs from
    #: `deletion_scheduled_for` by exactly the grace period, and the difference is
    #: computed once — so a change to `DELETION_GRACE_PERIOD` never moves an outstanding
    #: request's deadline.
    deletion_requested_at: str = ""
    onboarding: OnboardingStatusOut


class ProfileIn(Schema):
    """The profile write: the name to set.

    **One field, and the name is the whole of it.** The email is not editable here — it
    is the account's key, and changing it is a different operation with different
    consequences. The password is not here either; it is changed by the reset flow,
    which ends the account's other sessions.
    """

    name: str


class ProfileOut(Schema):
    """The profile after a write.

    **It carries the email and the id as well as the name**, so the client can update
    what it already knows without a second `me` call after a save — the name is the only
    thing that changed, but the answer is the caller's whole profile rather than a delta.
    """

    id: UUID
    email: str
    name: str
    #: Where to fetch this account's picture, or `""` when none is set.
    #:
    #: **A URL, not the key.** The key is internal; what a client can use is an address it
    #: can put in an `img`. See `CurrentUserOut.avatar_url` for why it is an app-owned URL
    #: rather than a signed one.
    avatar_url: str = ""


class EmailChangeRequestIn(Schema):
    """The email-change request: the address to move the login to."""

    new_email: str


class EmailChangeRequestOut(Schema):
    """The email-change answer. **The same for a free address and a taken one.**

    It says the request was received, and nothing about whether anybody already holds the
    address. Any difference here — a status, a field, a message — would turn this endpoint
    into an oracle for *"does an account exist at this address?"*, which is the thing the
    whole flow is shaped to avoid.
    """

    status: str = "accepted"


class EmailChangeCancelOut(Schema):
    """The cancel answer. The same whether something was pending or nothing was.

    Cancelling with nothing outstanding is not an error — the caller wanted no pending
    change and has none — so the response does not distinguish the two. A client that
    could tell them apart would be reading state it can already get from `me`.
    """

    status: str = "cancelled"


class EmailChangeConfirmIn(Schema):
    """The email-change confirmation: the token from the link sent to the new address."""

    token: str


class EmailChangeConfirmOut(Schema):
    """The confirmation answer: the login has moved.

    It carries the new address, because the caller may have no session — the link can be
    opened in a browser that never signed in — and a client that cannot read `me` still
    needs to be able to say what just happened.
    """

    status: str = "email_changed"
    email: str


class PasswordResetRequestIn(Schema):
    """The reset request: the address to reset."""

    email: str


class PasswordResetRequestOut(Schema):
    """The reset-request answer. The same for a known address and an unknown one.

    It says the request was received, and nothing about whether there is an account.
    """

    status: str = "accepted"


class PasswordResetConfirmIn(Schema):
    """The reset confirmation: the token from the reset link, and the new password."""

    token: str
    new_password: str


class PasswordResetConfirmOut(Schema):
    """The reset-confirmation answer.

    The password has been changed and the account's other sessions have ended.
    """

    status: str = "password_reset"


class CsrfTokenOut(Schema):
    """The CSRF token the frontend sends back on every unsafe request.

    The token is also set as the `csrftoken` cookie on the same response; the frontend
    reads the cookie and echoes the value in the `X-CSRFToken` header. Sending both is
    Django's own convention, and it is the one `CsrfViewMiddleware` checks.
    """

    csrf_token: str


class AccountDeletionCopyOut(Schema):
    """**What deleting this account would do — read before anything is asked.**

    **This is the preview.** The confirmation modal has to say what the deletion
    removes and what it leaves behind, and it has to say it *before* the person has
    typed anything. So the copy is read, not written into the frontend.

    ## One set of words, for two surfaces

    `what_is_deleted` and `what_survives` are the two sentences that say what the
    deletion does and what it leaves behind. **They are published here rather than
    written into the frontend**, because the mail already renders them — from the same
    two constants in `services.deletion` — and a second copy of the same sentence is a
    second place for the two surfaces to disagree.

    **The A-16 mockup's wording for these is not used, and that is not a
    preference.** The mockup's second paragraph ends *"We can't reverse deletion."*,
    which contradicts the thirty-day grace period the paragraph after it promises.
    **A modal that says both in consecutive paragraphs is a modal that lies**, and the
    backend's own wording — which the mail already ships — is the true one.

    ## It carries no state, on purpose

    **This read says what the engine does, and nothing about this account.** It is a
    constant of the product dressed as a read, and it is on this path because this is
    the only screen that asks the question. **The account's own pending state does not
    ride here** — `me` carries that, and it already does.

    **So there is nothing to cache and nothing to refresh.** The two strings never
    change, which is why the modal can read them once and open with its text already
    on screen.
    """

    #: What the deletion removes, in the product's own words. Never empty.
    what_is_deleted: str
    #: What survives it, as anonymised aggregates. Never empty.
    what_survives: str


class AccountDeletionRequestOut(AccountDeletionCopyOut):
    """The answer to "please delete my account": the request was recorded, and when it
    will take effect.

    **`scheduled_for` is the promise.** The thirty-day grace period is something the
    product told the person about, so the answer says exactly when the account will be
    destroyed — not "in about a month", not "soon". A person who cancels needs to know
    how long they have, and a person who wants to be sure the request landed needs to
    see the date that was set.

    **`requested_at` is when the request was recorded, and it can differ from
    `scheduled_for` by exactly the grace period.** The schedule is computed once, when
    the request is first made, so that a later request cannot move the date.

    **No reason field.** Nothing here records why somebody asked, and nothing here
    records what was deleted — the account is still there, in full, and the audit trail
    is where a record of the eventual deletion belongs.

    **It carries the copy too**, because a client that has just asked for the deletion
    wants to say what it did — and the copy is in this answer anyway, so asking for it
    again would be a second request for a string the server already sent.
    """

    status: str = "scheduled"
    requested_at: str
    scheduled_for: str


class AccountDeletionCancelOut(Schema):
    """The answer to "actually, don't": the pending request is gone.

    **Cancelling when nothing is pending is not an error.** The caller wanted no pending
    deletion and has none either way, so the answer is the same in both cases — the same
    reasoning as `EmailChangeCancelOut`, and for the same reason: a client that could
    tell the two apart would be reading state it can already get from `me`.
    """

    status: str = "cancelled"


class CheckoutIn(Schema):
    """The checkout request: which plan to buy.

    **The plan is the only field.** There is deliberately no `success_url`, no
    `cancel_url` and no `return_url`, and that absence is the security property rather
    than an oversight: the URLs handed to the provider are built from configuration, so a
    client cannot name one. Taking the redirect target from the request is the classic
    open-redirect in a checkout flow — a crafted target sends a paying user (and the
    session id in the query string) to somebody else's site.

    The plan is an enum, so an unknown one is a 422 at the edge rather than a provider
    error later.
    """

    plan: ProPlan


class CheckoutOut(Schema):
    """The checkout answer: the URL to send the user to.

    **It carries no entitlement, and asking for one here would be a lie.** The user is not
    Pro when this response is written; they are Pro when the provider's webhook lands,
    which may be later or never. So there is no `is_pro` field, no status and no plan
    echo: the answer is a URL and nothing else.
    """

    url: str


class PortalOut(Schema):
    """The portal answer: the URL to send the user to.

    Same shape as the checkout answer and for the same reason — the URL is the whole
    answer, and nothing about the subscription rides along with it.
    """

    url: str


class SubscriptionOut(Schema):
    """The caller's entitlement: one bool and nothing else.

    **The minimum, on purpose.** This answers exactly one question — *may this person buy
    a plan?* — and the answer is a bool. There is no plan name, no renewal date and no
    status here, because the fuller subscription record belongs to the account-and-billing
    surface, which needs a wider read and builds it there. A field here would be a field
    two callers could disagree about.

    **It is a read of the caller's own entitlement.** There is no user id in the request
    and none in the response: the user comes from the session, so a caller cannot ask
    about somebody else.
    """

    is_pro: bool


class BillingAccountOut(Schema):
    """The account screen's view of a plan (FR-48).

    **The wider read `SubscriptionOut` deliberately refused to become.** That schema stays
    one bool because *"a field here would be a field two callers could disagree about"*;
    this one carries the state a person needs to act on their own subscription, and the two
    cannot disagree because `is_pro` here is computed from the same
    `LIVE_SUBSCRIPTION_STATUSES` the entitlement read uses.

    **`needs_payment` is the field this schema exists for.** `is_pro` is true for a
    `past_due` account — a failed payment leaves someone entitled while they fix it — so a
    screen that could only see the bool would show a person with a recoverable problem
    exactly what it shows a person with none.

    **`period_end` is not a renewal date**, and is not named as one. This product does not
    model `cancel_at_period_end`, so a subscription cancelled in the provider's portal reads
    `active` until its term runs out and nothing here can tell them apart. The field says
    when the current term ends, which is true in both cases.
    """

    #: `active`, `past_due`, `canceled`, `expired` — or `null` for an account that never
    #: subscribed.
    status: str | None
    #: `monthly` or `yearly`, or `null`.
    plan: str | None
    #: When the current term ends, if known. **Not a renewal date** — see the docstring.
    period_end: str | None
    #: Whether Pro is available right now. True for `past_due`.
    is_pro: bool
    #: Whether a payment failed and the portal is where to fix it.
    needs_payment: bool
    #: Whether this account ever had Pro, so the Free state can read as "ended" rather than
    #: as "never started".
    had_pro: bool
