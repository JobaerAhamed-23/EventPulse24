"""The editorial app's admin module (AD-14).

**This app registers no `ModelAdmin` of its own, and that is deliberate.** Django's
`admin.site.register` needs the model class, and the `models-ingestion` import-linter
contract says only `apps.ingestion` may import `apps.ingestion.models`. A `ModelAdmin`
for `ReviewItem` written here would break AD-2 on import.

So the FR-57 review queue is rendered by `apps/ingestion/admin.py`, next to the table it
renders — `ingestion` owns `REVIEW_ITEM` (AD-16), and *"an app's admin lives in that
app"*. What lives here is the **editorial reading** of that queue: the facts a reviewer
needs, and the rule about who may work it.

**Where each concern lives:**

- The queue's `ModelAdmin`, its forms and its four verdicts —
  `apps/ingestion/admin.py`.
- The queue's read service, the facts and the metrics —
  `apps/ingestion/services/review_queue_read.py`.
- The queue's verdicts, the commands — `apps/ingestion/services/editorial_review.py`.
- **Who may work the queue, and the reviewer's view of it** —
  `apps/editorial/services/review_queue.py`.

Django groups its admin index by `model._meta.app_label`, so the queue appears under
**Ingestion**. A second `AdminSite` would give the editorial group its own index — and
its own login, its own permission namespace and its own `LogEntry`, which is a *second
privileged surface*. AD-14 exists to prevent exactly that, so there is one admin site,
one permission model and one audit log, and the editorial group is a group of permissions
within it.

This module re-exports the editorial service's published names, so a caller that wants
the editorial view imports it from here rather than reaching into `services`.
"""

from apps.editorial.services.review_queue import (
    EDITORIAL_GROUP,
    REVIEW_CHANGE_PERMISSION,
    REVIEW_PERMISSIONS,
    REVIEW_VIEW_PERMISSION,
    QueueView,
    editor_name,
    may_review,
    may_view,
    queue_view,
)

__all__ = [
    "EDITORIAL_GROUP",
    "REVIEW_CHANGE_PERMISSION",
    "REVIEW_PERMISSIONS",
    "REVIEW_VIEW_PERMISSION",
    "QueueView",
    "editor_name",
    "may_review",
    "may_view",
    "queue_view",
]
