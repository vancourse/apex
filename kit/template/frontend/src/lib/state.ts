import type { ScreenState } from "../gen/registry";
import type { LoadError } from "./load";

export { SCREEN_STATES, type ScreenState } from "../gen/registry";

/** Compile-time exhaustiveness: a `switch` over ScreenState that misses a case fails typecheck. */
export function assertNever(value: never): never {
  throw new Error(`unhandled screen state: ${String(value)}`);
}

/** The screen state a failed load puts the screen in. */
export function stateForError(error: LoadError): ScreenState {
  switch (error.kind) {
    case "unauthenticated":
      return "unauthenticated";
    case "disabled_503":
      return "disabled_503";
    case "not_composed":
      return "not_composed";
    case "timeout":
    case "failed":
      return "failed";
    default:
      return assertNever(error);
  }
}
