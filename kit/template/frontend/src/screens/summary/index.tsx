import { useState } from "react";
import type { Api } from "../../gen/client";
import type { EntryList, Me, Summary } from "../../gen/types";
import { Figure } from "../../lib/figure";
import { toLoadError, useLoad, type Load, type LoadError } from "../../lib/load";
import { assertNever, stateForError, type ScreenState } from "../../lib/state";

export type WriteStatus =
  | { readonly kind: "idle" }
  | { readonly kind: "saving" }
  | { readonly kind: "invalid"; readonly message: string }
  | { readonly kind: "failed"; readonly error: LoadError };

/** Every input to the screen decides exactly one ScreenState. */
export function deriveState(
  me: Load<Me>,
  summary: Load<Summary>,
  entries: Load<EntryList>,
  write: WriteStatus,
): ScreenState {
  if (me.kind === "err") return stateForError(me.error);
  if (summary.kind === "err") return stateForError(summary.error);
  if (me.kind === "pending" || summary.kind === "pending" || entries.kind === "pending") return "loading";
  if (entries.kind === "err") return "partial";
  if (write.kind === "failed") return "write_failed";
  return entries.value.entries.length === 0 ? "empty" : "loaded";
}

const AMOUNT = /^-?\d+$/;

export function SummaryScreen({ api }: { api: Api }) {
  const [version, setVersion] = useState(0);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [write, setWrite] = useState<WriteStatus>({ kind: "idle" });

  const me = useLoad(() => api.me(), [api, version]);
  const household = me.kind === "ok" ? me.value.household_id : null;
  const summary = useLoad(() => (household === null ? null : api.getSummary(household)), [api, household, version]);
  const entries = useLoad(() => (household === null ? null : api.listEntries(household)), [api, household, version]);
  const state = deriveState(me, summary, entries, write);

  async function add(): Promise<void> {
    if (household === null) return;
    if (!AMOUNT.test(amount.trim())) {
      setWrite({ kind: "invalid", message: "Enter a whole number of cents." });
      return;
    }
    setWrite({ kind: "saving" });
    try {
      await api.postEntry(household, { amount_cents: Number.parseInt(amount.trim(), 10), note });
      setAmount("");
      setNote("");
      setWrite({ kind: "idle" });
      setVersion((v) => v + 1);
    } catch (thrown) {
      setWrite({ kind: "failed", error: toLoadError(thrown) });
    }
  }

  return (
    <section className={`screen state-${state}`} data-screen="summary" data-state={state}>
      <header>
        <h1>Summary</h1>
        <button type="button" data-control="summary.refresh" onClick={() => setVersion((v) => v + 1)}>
          Refresh
        </button>
      </header>
      <Body state={state} summary={summary} entries={entries} write={write} />
      {household !== null && state !== "loading" && (
        <form
          className="add-entry"
          onSubmit={(event) => {
            event.preventDefault();
            void add();
          }}
        >
          <label>
            Amount (cents)
            <input
              data-control="summary.amount"
              inputMode="numeric"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>
          <label>
            Note
            <input data-control="summary.note" value={note} onChange={(event) => setNote(event.target.value)} />
          </label>
          <button type="submit" data-control="summary.add" disabled={write.kind === "saving"}>
            Add entry
          </button>
          {write.kind === "invalid" && <p role="alert">{write.message}</p>}
        </form>
      )}
    </section>
  );
}

function Body({
  state,
  summary,
  entries,
  write,
}: {
  state: ScreenState;
  summary: Load<Summary>;
  entries: Load<EntryList>;
  write: WriteStatus;
}) {
  switch (state) {
    case "loading":
      return <p className="status">Loading...</p>;
    case "unauthenticated":
      return <p className="status">Sign in to see this household.</p>;
    case "disabled_503":
      return <p className="status">The server is temporarily unavailable. Try again shortly.</p>;
    case "not_composed":
      return <p className="status">This screen is not available on this server.</p>;
    case "failed":
      return <p className="status">This month could not be loaded.</p>;
    case "partial":
    case "write_failed":
    case "empty":
    case "loaded":
      return (
        <>
          {summary.kind === "ok" && (
            <p className="month-total">
              Month total for {summary.value.month}:{" "}
              <Figure concept="month_total" value={summary.value.month_total_cents} />
            </p>
          )}
          {state === "write_failed" && write.kind === "failed" && (
            <p role="alert">The entry was not saved ({write.error.kind}).</p>
          )}
          {state === "partial" && <p className="status">Entries could not be loaded.</p>}
          {state === "empty" && summary.kind === "ok" && <p className="status">No entries in {summary.value.month}.</p>}
          {entries.kind === "ok" && entries.value.entries.length > 0 && (
            <ul className="entries">
              {entries.value.entries.map((entry) => (
                <li key={entry.id}>
                  <span>{entry.occurred_on}</span> <span>{entry.note}</span>{" "}
                  <Figure concept="entry_amount" value={entry.amount_cents} />
                </li>
              ))}
            </ul>
          )}
        </>
      );
    default:
      return assertNever(state);
  }
}
