import { settingInt, settingText } from "../gen/settings";
import { ApiError, type LoadError } from "./load";

// The ONLY module that calls fetch (eslint `local/no-raw-fetch`); screens use the
// generated client in src/gen/client.ts, which goes through a Transport.

export type FetchLike = (
  url: string,
  init: { method: string; headers: Record<string, string>; body?: string; signal: AbortSignal },
) => Promise<{ status: number; json(): Promise<unknown> }>;

export interface Transport {
  request<T>(
    method: string,
    path: string,
    options?: { query?: Record<string, string | undefined>; body?: unknown },
  ): Promise<T>;
}

export function errorForStatus(status: number, message: string): LoadError {
  if (status === 401) return { kind: "unauthenticated" };
  if (status === 503) return { kind: "disabled_503" };
  if (status === 404) return { kind: "not_composed" };
  return { kind: "failed", status, message };
}

/** DEV ONLY: the planted member token rides in `?member=` and is sent as X-Member. */
function memberFromLocation(): string | null {
  return new URLSearchParams(window.location.search).get("member");
}

export function makeTransport(
  options: { fetchImpl?: FetchLike; base?: string; member?: string | null; timeoutMs?: number } = {},
): Transport {
  const fetchImpl: FetchLike =
    options.fetchImpl === undefined ? (globalThis.fetch.bind(globalThis) as unknown as FetchLike) : options.fetchImpl;
  const base = options.base === undefined ? settingText("API_BASE") : options.base;
  const timeoutMs = options.timeoutMs === undefined ? settingInt("REQUEST_TIMEOUT_MS") : options.timeoutMs;

  return {
    async request<T>(
      method: string,
      path: string,
      opts: { query?: Record<string, string | undefined>; body?: unknown } = {},
    ): Promise<T> {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(opts.query === undefined ? {} : opts.query)) {
        if (value !== undefined) params.set(key, value);
      }
      const search = params.toString();
      const member = options.member === undefined ? memberFromLocation() : options.member;
      const headers: Record<string, string> = { Accept: "application/json" };
      if (member !== null) headers["X-Member"] = member;
      if (opts.body !== undefined) headers["Content-Type"] = "application/json";

      const controller = new AbortController();
      const timedOut = new Promise<never>((_, reject) => {
        controller.signal.addEventListener("abort", () => reject(new ApiError({ kind: "timeout" })));
      });
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        let response: Awaited<ReturnType<FetchLike>>;
        try {
          response = await Promise.race([
            fetchImpl(base + path + (search ? `?${search}` : ""), {
              method,
              headers,
              body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
              signal: controller.signal,
            }),
            timedOut,
          ]);
        } catch (thrown) {
          if (thrown instanceof ApiError) throw thrown;
          throw new ApiError({ kind: "failed", status: null, message: "network error" });
        }
        if (response.status >= 200 && response.status < 300) return (await response.json()) as T;
        throw new ApiError(errorForStatus(response.status, `HTTP ${response.status}`));
      } finally {
        clearTimeout(timer);
      }
    },
  };
}
