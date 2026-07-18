/**
 * Provider-agnostic analytics abstraction.
 *
 * The app talks only to the `track` / `pageView` interface below. Swapping in a
 * real provider later (PostHog, GA, Segment, …) means adding a class that
 * implements `AnalyticsProvider` and selecting it in `getAnalytics()` — no
 * call-site changes. No external service is wired up yet.
 */

export interface AnalyticsEvent {
  name: string;
  properties?: Record<string, unknown>;
}

export interface AnalyticsProvider {
  track(event: AnalyticsEvent): void;
  pageView(path: string): void;
}

/** Discards everything. Default until a real provider is configured. */
export class NoopAnalytics implements AnalyticsProvider {
  track(): void {
    /* no-op */
  }
  pageView(): void {
    /* no-op */
  }
}

/** Logs to the console — useful during local development. */
export class ConsoleAnalytics implements AnalyticsProvider {
  track({ name, properties }: AnalyticsEvent): void {
    // eslint-disable-next-line no-console
    console.debug("[analytics] track", name, properties ?? {});
  }
  pageView(path: string): void {
    // eslint-disable-next-line no-console
    console.debug("[analytics] pageView", path);
  }
}

let provider: AnalyticsProvider | null = null;

/** Returns the active provider, lazily selected from the environment. */
export function getAnalytics(): AnalyticsProvider {
  if (provider) return provider;
  const useConsole =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_ANALYTICS !== "disabled";
  provider = useConsole ? new ConsoleAnalytics() : new NoopAnalytics();
  return provider;
}

/** Fire a custom event. */
export function track(name: string, properties?: Record<string, unknown>): void {
  getAnalytics().track({ name, properties });
}

/** Fire a page-view event for the given path. */
export function pageView(path: string): void {
  getAnalytics().pageView(path);
}
