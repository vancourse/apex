import { useEffect, useState, type DependencyList } from "react";

/** Why a load did not produce a value. Each kind maps to one ScreenState. */
export type LoadError =
  | { readonly kind: "unauthenticated" }
  | { readonly kind: "disabled_503" }
  | { readonly kind: "not_composed" }
  | { readonly kind: "timeout" }
  | { readonly kind: "failed"; readonly status: number | null; readonly message: string };

export type Ok<T> = { readonly kind: "ok"; readonly value: T };
export type Err<E> = { readonly kind: "err"; readonly error: E };
export type Result<T, E> = Ok<T> | Err<E>;

/** A load in flight, or its Result. There is no `T | undefined` to `?? []` away. */
export type Load<T> = { readonly kind: "pending" } | Result<T, LoadError>;

export class ApiError extends Error {
  constructor(readonly error: LoadError) {
    super(error.kind === "failed" ? error.message : error.kind);
  }
}

export function toLoadError(thrown: unknown): LoadError {
  if (thrown instanceof ApiError) return thrown.error;
  return { kind: "failed", status: null, message: String(thrown) };
}

/**
 * Run `fn` whenever `deps` change. `fn` returning null means "not yet" (a
 * dependency is still loading) and leaves the result pending.
 */
export function useLoad<T>(fn: () => Promise<T> | null, deps: DependencyList): Load<T> {
  const [state, setState] = useState<Load<T>>({ kind: "pending" });
  useEffect(() => {
    let live = true;
    setState({ kind: "pending" });
    const promise = fn();
    if (promise !== null) {
      promise.then(
        (value) => {
          if (live) setState({ kind: "ok", value });
        },
        (thrown: unknown) => {
          if (live) setState({ kind: "err", error: toLoadError(thrown) });
        },
      );
    }
    return () => {
      live = false;
    };
    // `fn` is re-created every render; `deps` are the inputs that matter.
  }, deps);
  return state;
}
