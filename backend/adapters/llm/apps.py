from django.apps import AppConfig


class LlmConfig(AppConfig):
    """`adapters.llm` is a Django app so it can own the AI cost table (AD-8).

    **Why an adapter is a Django app.** The coding standard says the gateway writes "a
    per-call cost row in the same transaction as the result", and that under
    `apps | adapters` the gateway cannot import an app's models. So the model lives
    here, with `adapters.llm` registered as an app and routed to the `catalog` schema.

    **The label is `llm`, not `adapters_llm`.** Django derives a default label from the
    last component of the app name, which would be `llm` — but being explicit means the
    label is a decision rather than an accident of the package's name.
    """

    name = "adapters.llm"
    label = "llm"
