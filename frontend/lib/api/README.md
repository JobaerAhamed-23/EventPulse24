# `lib/api/`: generated API client

Everything in this folder except this README is **generated** from the backend's OpenAPI schema
(AD-19) and **never edited by hand**. Regenerate it instead; CI fails if the committed client
differs from what the schema produces.

The generator (`make client`) arrives with the `health-round-trip` work item. Frontend code
reaches the backend only through this client: no hand-written `fetch` to backend routes.
