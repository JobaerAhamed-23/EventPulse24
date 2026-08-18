# EventPulse24
### AI-Powered Personalized Event Notification Platform
**Product Requirements & System Design Document**

Version 1.0
Prepared: August 2026

---

## 1. Executive Summary

EventPulse24 is an AI-assisted web platform that keeps users informed about events that matter to them — automatically discovered global, national/local, sports, technology, and government events, as well as events users create themselves (meetings, occasions, get-togethers, and more). The platform uses AI-driven web crawling to continuously discover and structure event data from the internet, and it lets users control exactly when they're reminded, from 5 days ahead down to 1 hour before an event starts.

This document defines the product scope, features, data model, system architecture, and notification logic required to build EventPulse24.

---

## 2. Problem Statement

People currently rely on scattered sources — social media, individual websites, calendars, and word of mouth — to keep track of events relevant to their interests. This leads to:

- Missed sports fixtures, tech conferences, government deadlines, and community events.
- No single place to combine public/global events with personal events (meetings, birthdays, get-togethers).
- Generic, one-size-fits-all reminders instead of personalized timing and topic preferences.
- Manual effort required to discover new events, since no single source aggregates them all.

---

## 3. Goals & Objectives

1. Automatically discover and catalog events across categories using AI-powered web crawling.
2. Allow any user to manually create and manage their own events (public or private).
3. Let users personalize which categories/topics they follow and how far in advance they're notified.
4. Deliver timely, reliable, multi-channel notifications (web push, email, SMS — phased).
5. Provide a scalable, moderated system where crawled data is trustworthy and de-duplicated.

---

## 4. Target Users & Personas

| Persona | Description | Primary Need |
|---|---|---|
| General Consumer | Wants to stay updated on sports, tech, and local happenings | Curated, relevant global/local event feed |
| Professional | Attends conferences, government/policy events, industry meetups | Reliable early reminders, calendar sync |
| Individual / Family User | Tracks personal occasions — birthdays, meetings, get-togethers | Easy personal event creation & private reminders |
| Community Organizer | Publishes local or club events for others to discover | Simple event publishing with reach to relevant users |
| Admin / Moderator | Oversees crawled data quality and platform health | Moderation tools, source management, analytics |

---

## 5. Event Taxonomy

Events are organized along two dimensions: **Scope** (who it's relevant to) and **Topic** (what it's about). This dual structure lets the recommendation engine match events to user preferences accurately.

### 5.1 By Scope

| Scope | Description | Source |
|---|---|---|
| Global Events | Worldwide relevance — e.g. World Cup, global tech launches, international summits | AI crawler |
| National / Local Events | Country, city, or region-specific — elections, local festivals, regional matches | AI crawler + community-submitted |
| Personal Events | Private to the user or their invited group — meetings, occasions, get-togethers | User-created only |

### 5.2 By Topic (applies to Global & National/Local events)

- Sports — matches, tournaments, league fixtures, championships
- Technology — product launches, conferences, hackathons, webinars
- Government / Civic — elections, policy deadlines, public consultations, holidays
- Other Global/Community — entertainment, culture, finance, education, and general interest events

Topics are extensible — new topics can be added via the admin panel without code changes.

---

## 6. Core Features

### 6.1 AI-Powered Event Discovery Engine
An automated pipeline continuously crawls external websites (news sites, sports federations, government portals, ticketing platforms, tech-conference sites, etc.), uses AI (LLM-based extraction) to identify event information within unstructured page content, and normalizes it into structured event records (title, date/time, location, category, source link, description).

### 6.2 User-Generated Events
Any registered user can create an event of any scope they're permitted to (personal events always allowed; local/community events may require verification). Fields include title, description, date/time, timezone, location (physical or virtual), category, visibility (private, invite-only, public), and optional recurring rules.

### 6.3 Personalized Notification Engine
Users configure notification lead times per category or per individual event. Multiple lead times can be active simultaneously (e.g. 5 days AND 1 day AND 1 hour before).

| Lead Time Option | Typical Use Case |
|---|---|
| 5 days before | Trip/travel planning, ticket purchase reminders |
| 2 days before | Preparation, RSVP finalization |
| 1 day before | Final preparation, packing, logistics |
| 1 hour before | Immediate heads-up / "leave now" reminder |
| Custom | User-defined minutes/hours/days (e.g. 30 min, 3 days, 1 week) |

### 6.4 Preference & Personalization Center
- Follow/unfollow categories and topics (Sports, Tech, Government, etc.)
- Set location filters (country, state/region, city) for national/local events
- Set default and per-category notification lead times
- Choose notification channels: in-app, email, push, SMS (phased rollout)
- Mute or snooze specific event series or sources

### 6.5 Search & Discovery
- Keyword search across all public events
- Filter by category, scope, date range, and location
- "Trending" and "Recommended for you" feeds driven by user preference and behavior

### 6.6 Calendar & Integrations
- Personal calendar view (day/week/month/agenda)
- Export/sync to Google Calendar, Outlook, Apple Calendar (.ics)

### 6.7 Roles & Permissions

| Role | Capabilities |
|---|---|
| Guest | Browse public global/local events (no notifications, no personal events) |
| Registered User | All browsing + create personal events + set notification preferences |
| Verified Organizer | Publish public local/community events visible to other users |
| Admin / Moderator | Manage crawler sources, approve/reject flagged events, manage categories, view analytics |

---

## 7. Notification System — Functional Rules

1. Each event has one or more scheduled trigger times, computed as Event Start Time minus each active lead-time setting.
2. A background scheduler (job queue) evaluates upcoming triggers and dispatches notifications at the correct time, accounting for the user's timezone.
3. If a user updates an event's time after notifications are scheduled, all pending triggers for that event are recalculated automatically.
4. Users can set notification preferences at three levels, with the most specific taking precedence: (1) Global default, (2) Per-category, (3) Per-event override.
5. Duplicate/overlapping notifications for the same event and lead time are suppressed (idempotent delivery).
6. Delivery channel fallback: if push delivery fails, fall back to email (configurable).
7. All notifications are logged for delivery-status tracking and are visible in an in-app notification center/history.

---

## 8. System Architecture (High Level)

The platform is composed of five major subsystems:

### 8.1 Client Layer
- Responsive web app (primary) — event feed, calendar, event creation, preference center
- Progressive Web App / mobile-friendly UI for push notification support

### 8.2 Application / API Layer
- REST or GraphQL API serving events, users, preferences, and notifications
- Authentication & authorization service (OAuth / JWT-based sessions)
- Event management service (CRUD for user-created events)

### 8.3 AI Crawling & Ingestion Pipeline
1. **Source Manager** — curated list of target websites/APIs per category (sports federations, government portals, tech-event listing sites, news outlets).
2. **Crawler/Scraper Workers** — scheduled jobs that fetch page content (respecting robots.txt and site terms).
3. **AI Extraction Layer** — LLM-based parser that reads raw page content and extracts structured fields (title, date, time, location, category, description, source URL) with confidence scoring.
4. **Deduplication & Normalization** — matches newly extracted events against existing records (fuzzy match on title + date + location) to avoid duplicates; normalizes date/time to UTC + source timezone.
5. **Moderation Queue** — low-confidence or flagged extractions are queued for admin/human review before publishing.
6. **Publisher** — approved events are written to the primary Events database and become visible/searchable.

### 8.4 Notification & Scheduling Layer
- Job scheduler / message queue (e.g. cron + queue workers) that evaluates trigger times
- Notification dispatch service integrating with push, email, and SMS providers
- Delivery log & retry handling

### 8.5 Data & Storage Layer
- Primary relational database for Users, Events, Preferences, Notifications
- Search index (e.g. full-text/vector search) for fast event discovery and AI similarity matching
- Object storage for event images/attachments
- Cache layer for frequently accessed feeds

---

## 9. Data Model (Core Entities)

### 9.1 User
`user_id, name, email, password_hash/OAuth_id, location, timezone, role, created_at`

### 9.2 Event
`event_id, title, description, scope (global/national-local/personal), category/topic, start_datetime, end_datetime, timezone, location (text + geo-coordinates), visibility, source_type (crawled/user-created), source_url, created_by, status (pending/approved/published/archived), confidence_score`

### 9.3 Category
`category_id, name, parent_category (for sub-topics), description`

### 9.4 Notification Preference
`preference_id, user_id, scope (global-default/category/event), category_id (nullable), event_id (nullable), lead_times[] (e.g. [5d, 1d, 1h]), channels[] (email/push/sms)`

### 9.5 Notification Log
`notification_id, user_id, event_id, trigger_time, channel, status (scheduled/sent/failed), sent_at`

### 9.6 Source (for crawler)
`source_id, name, url, category_focus, crawl_frequency, last_crawled_at, reliability_score`

---

## 10. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Scalability | Support growing volume of crawled events and concurrent notification dispatch; horizontally scalable workers |
| Reliability | Notification delivery success rate target ≥ 99%; retry with backoff on failure |
| Data Quality | AI-extracted events pass a confidence threshold or route to human moderation |
| Privacy & Security | Personal events are private by default; role-based access control; encrypted credentials; GDPR-style data export/delete |
| Compliance | Crawling respects robots.txt, site terms of service, and rate limits |
| Performance | Event feed loads within 2 seconds for typical queries |
| Localization | Multi-timezone support; multi-language ready (future) |

---

## 11. Suggested Technology Stack

| Layer | Suggested Options |
|---|---|
| Frontend | React / Next.js, Tailwind CSS |
| Backend / API | Node.js (NestJS/Express) or Python (FastAPI/Django) |
| Database | PostgreSQL (primary), Redis (cache/queue) |
| Search | Elasticsearch / OpenSearch or a vector DB for semantic matching |
| AI Extraction | LLM API (e.g. Claude) for content parsing and structuring |
| Crawling | Scrapy / Playwright workers orchestrated via a job queue (e.g. Celery, BullMQ) |
| Notifications | Web Push (VAPID), email provider (SES/SendGrid), SMS provider (Twilio) |
| Hosting/Infra | Docker containers on a cloud provider (AWS/GCP/Azure); CI/CD pipeline |

---

## 12. Key User Flows

### 12.1 Onboarding
1. User signs up → selects location → selects interested categories (Sports, Tech, Government, etc.) → sets default notification lead times → lands on personalized event feed.

### 12.2 Discovering a Crawled Event
1. AI crawler finds new event on a source site → extraction + confidence scoring → auto-publish (high confidence) or moderation queue (low confidence) → event appears in matching users' feeds → notifications scheduled.

### 12.3 Creating a Personal Event
1. User clicks "Create Event" → fills details (title, date/time, location, visibility) → chooses notification lead times → optionally invites others → event saved and reminders scheduled.

### 12.4 Receiving a Notification
1. Scheduler detects trigger time reached → notification dispatched via preferred channel(s) → logged → appears in in-app notification center.

---

## 13. Content Moderation & Trust

- Confidence scoring on every AI-extracted event; below-threshold items require human review.
- Duplicate detection before publishing to keep the feed clean.
- User-reporting mechanism to flag incorrect or spam events.
- Source reliability scoring to prioritize trustworthy crawl targets over time.

---

## 14. Phased Roadmap

| Phase | Scope |
|---|---|
| Phase 1 – MVP | User auth, personal event creation, manual category follow, basic email/in-app notifications (1 day / 1 hour presets) |
| Phase 2 – AI Crawling | Source manager, crawler workers, AI extraction pipeline, moderation queue, auto-published global/national events |
| Phase 3 – Personalization | Custom lead times, per-category preferences, recommended/trending feeds, push + SMS channels |
| Phase 4 – Scale & Integrations | Calendar sync (Google/Outlook/Apple), organizer verification, analytics dashboard, multi-language support |

---

## 15. Success Metrics (KPIs)

- Number of active users with at least one notification preference configured
- Notification delivery success rate and average delivery latency
- Number of AI-crawled events auto-published vs. sent to moderation
- User-created events per week
- Event feed click-through and RSVP/attendance rate
- Duplicate event rate post-deduplication (target: near zero)

---

## 16. Open Questions for Stakeholders

1. Which regions/countries and which specific source websites should be prioritized for the initial crawler rollout?
2. Should organizer verification be required before a user's local event is publicly visible to others?
3. What notification channels are required at launch — is SMS needed for MVP, or can it be phased in later?
4. What is the target scale (expected users, expected events/day from crawling) to size infrastructure correctly?
