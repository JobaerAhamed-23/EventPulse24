import { AddEventButton } from "@/components/add-event-button";
import { PersonalEventsSection } from "@/components/personal-events-section";

export default function HomePage() {
  return (
    <main className="fade-in mx-auto max-w-(--layout-container-reading) px-6 py-20">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">EventPulse24</h1>
          <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-lg)]">
            What&apos;s actually worth your attention right now.
          </p>
        </div>
        {/* The spine's "Add" affordance: it opens the create sheet in place, and it does
            not route anywhere. The sidenav that will carry it does not exist yet. */}
        <AddEventButton />
      </div>

      <section className="mt-12" aria-label="Your personal events">
        <PersonalEventsSection />
      </section>
    </main>
  );
}
