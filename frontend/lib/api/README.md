# `lib/api/`: generated API contract

Everything in this folder except this README is **generated** and **never edited by hand** (AD-19):

| File           | Made by                                                 | From           |
| -------------- | ------------------------------------------------------- | -------------- |
| `openapi.json` | `make openapi` (Django Ninja's `export_openapi_schema`) | the live API   |
| `schema.ts`    | `make client` (`openapi-typescript`)                    | `openapi.json` |

After changing an API endpoint, run `make client` and commit both files. The backend suite fails
(`tests/api/test_contract.py`) until `openapi.json` matches the API, and CI regenerates both and
fails on any diff.

Frontend code reaches the backend only through `api` from `@/lib/backend-client`, which is typed
from `schema.ts`. ESLint rejects hand-written `fetch` calls in `app/` and `components/`.
