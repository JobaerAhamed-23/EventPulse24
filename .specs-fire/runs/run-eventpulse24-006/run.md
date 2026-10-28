---
id: run-eventpulse24-006
scope: single
work_items:
  - id: ports-fakes-and-worker
    intent: project-scaffold
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-27T14:25:28.646Z
completed: 2026-10-27T15:11:25.178Z
---

# Run: run-eventpulse24-006

## Scope
single (1 work item)

## Work Items
1. **ports-fakes-and-worker** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/ports/email.py`: Stream, EmailMessage, SendResult, EmailPort (AD-20 checks in final send; adapters implement _deliver)
- `backend/ports/llm.py`: LLMRequest/LLMResult/LLMPort starter shape (AD-8, AD-9)
- `backend/ports/embedding.py`: EmbeddingResult/EmbeddingPort
- `backend/ports/billing.py`: ProPlan, BillingCustomer, CheckoutSession, PortalSession, BillingPort
- `backend/ports/calendar.py`: Credential, CalendarFeed, CalendarEntry, CalendarPort (AD-18)
- `backend/ports/registry.py`: get_<x>_port(): adapter from settings.ADAPTERS with subclass check
- `backend/adapters/email/smtp.py`: SmtpEmailAdapter (Mailpit locally; stream, idempotency and RFC 8058 headers)
- `backend/adapters/email/memory.py`: InMemoryEmailAdapter for tests
- `backend/adapters/llm/fake.py`: FakeLLMAdapter, FakeEmbeddingAdapter (deterministic, free)
- `backend/adapters/billing/fake.py`: FakeBillingAdapter
- `backend/adapters/calendar/fake.py`: FakeCalendarAdapter
- `backend/config/adapters.py`: Adapter table per ADAPTER_MODE; real fails fast
- `backend/config/celery.py`: Celery app, static 60s tick beat_schedule, logging + trace-id signals
- `backend/config/management/commands/send_test_email.py`: Manual Mailpit check through the email port
- `backend/worker/tasks.py`: tick task (AD-7 seed)
- `backend/tests/ports/test_email_port.py`: AD-20 send rules
- `backend/tests/ports/test_registry.py`: Adapter selection by settings
- `backend/tests/config/test_adapters.py`: ADAPTER_MODE tables
- `backend/tests/config/test_send_test_email.py`: send_test_email command
- `backend/tests/adapters/test_email_smtp.py`: SMTP adapter headers via test outbox
- `backend/tests/adapters/test_fakes.py`: Fake adapters and Credential
- `backend/tests/worker/test_tick.py`: Tick and beat schedule
- `backend/tests/worker/test_trace_id.py`: Trace id into jobs incl. real in-process worker

## Files Modified
- `backend/pyproject.toml`: celery[redis]==5.6.3
- `backend/uv.lock`: celery 5.6.3, kombu 5.6.2, redis 6.4.0 and deps
- `backend/config/__init__.py`: Expose celery_app
- `backend/config/settings.py`: ADAPTERS, MAILERS (Mailpit), CELERY_* settings
- `backend/adapters/logging/formatter.py`: Framework log args: exceptions to type names; celery.app.trace keeps only name/id/runtime/description
- `backend/adapters/logging/redaction.py`: URL credential pattern also matches password-only URLs (review fix)
- `backend/tests/adapters/test_logging.py`: Celery line redaction and password-only URL tests
- `Makefile`: worker (--pool solo), beat (pidfile guard), send-test-email
- `.gitignore`: backend/.celery/
- `README.md`: Worker, beat, test email, fake adapters
- `docs/setup/macos.md`: Worker/beat section; Docker Desktop CLI PATH troubleshooting
- `docs/setup/ubuntu.md`: Worker/beat section
- `.specs-fire/standards/tech-stack.md`: celery[redis] 5.6.3, redis 6.4.0 (kombu cap), solo pool
- `.specs-fire/standards/coding-standards.md`: Port registry, ABC ports, EmailPort.send rules, Celery logging and trace rules
- `.specs-fire/intents/project-scaffold/work-items/health-round-trip.md`: Hand-off: make dev runs one worker and exactly one beat

## Decisions
- **Port depth**: Small starter set: 1-2 actions per port (User choice; feature intents reshape them)
- **Worker pool**: --pool solo on both macOS and Ubuntu (User choice; Celery 5.6.3 prefork fails on macOS (spawn); identical setup on both machines)
- **Adapter selection**: settings.ADAPTERS dotted paths resolved by ports.registry; ADAPTER_MODE=real fails at startup (Apps never import adapters; no silent fakes where real services are expected)
- **AD-20 enforcement**: Final EmailPort.send validates stream, bulk unsubscribe URL and idempotency key; adapters implement _deliver (One rule for every adapter; send without stream is a TypeError)
- **Celery log lines**: Withhold return values and exception text from celery.app.trace; exception args become type names (AD-13: exception messages and payloads never reach the log sink)
- **Password-only URL scrubbing**: Fixed in this run (User choice; managed Redis URLs often have no user part)
- **Email settings**: Django 6.1 MAILERS instead of EMAIL_HOST/EMAIL_PORT (Avoid RemovedInDjango2028Warning)


## Summary

- Work items completed: 1
- Files created: 23
- Files modified: 15
- Tests added: 66
- Coverage: 0%
- Completed: 2026-10-27T15:11:25.178Z
