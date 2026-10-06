import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { makeApi } from "../../gen/client";
import { makeTransport, type FetchLike } from "../../lib/client";
import { SCREEN_STATES, type ScreenState } from "../../lib/state";
import { SummaryScreen } from "./index";

// The state matrix: a stub transport that rejects, 503s, 404s, times out and
// returns empty, and the screen must render the matching ScreenState for each.
// The last test fails if any ScreenState in contracts/registry.py was never produced.

const HOUSEHOLD = "hh_scratch";
const ME = { member_id: "m_kit", household_id: HOUSEHOLD, display_name: "Kit" };
const SUMMARY = { household_id: HOUSEHOLD, month: "2026-02", month_total_cents: 6024 };
const ENTRY = {
  id: "e1",
  household_id: HOUSEHOLD,
  member_id: "m_kit",
  amount_cents: 1999,
  occurred_on: "2026-02-01",
  note: "bus pass",
};

type Reply = ReturnType<FetchLike>;
const reply = (status: number, body: unknown = {}): Reply => Promise.resolve({ status, json: () => Promise.resolve(body) });
const hang = (): Reply => new Promise(() => undefined);

function stub(overrides: Record<string, () => Reply>): FetchLike {
  const routes: Record<string, () => Reply> = {
    "GET /api/me": () => reply(200, ME),
    [`GET /api/households/${HOUSEHOLD}/summary`]: () => reply(200, SUMMARY),
    [`GET /api/households/${HOUSEHOLD}/entries`]: () =>
      reply(200, { household_id: HOUSEHOLD, month: "2026-02", entries: [ENTRY] }),
    ...overrides,
  };
  return (url, init) => {
    const handler = routes[`${init.method} ${url.split("?")[0]}`];
    return handler === undefined ? reply(404) : handler();
  };
}

const produced = new Set<ScreenState>();

function mount(fetchImpl: FetchLike, timeoutMs = 2000) {
  const api = makeApi(makeTransport({ fetchImpl, base: "", member: "planted-kit", timeoutMs }));
  return render(<SummaryScreen api={api} />);
}

async function expectState(container: HTMLElement, state: ScreenState): Promise<void> {
  await waitFor(() => {
    const section = container.querySelector("[data-state]");
    expect(section?.getAttribute("data-state")).toBe(state);
    expect(section?.classList.contains(`state-${state}`)).toBe(true);
  });
  produced.add(state);
}

afterEach(cleanup);

describe("summary screen states", () => {
  it("loading: nothing has answered yet", async () => {
    const { container } = mount(stub({ "GET /api/me": hang }));
    await expectState(container, "loading");
  });

  it("loaded: figures render through <Figure>", async () => {
    const { container, getByText } = mount(stub({}));
    await expectState(container, "loaded");
    expect(getByText("60.24")).toBeTruthy();
    expect(getByText("19.99")).toBeTruthy();
  });

  it("empty: the month has no entries", async () => {
    const { container, getByText } = mount(
      stub({ [`GET /api/households/${HOUSEHOLD}/entries`]: () => reply(200, { ...SUMMARY, entries: [] }) }),
    );
    await expectState(container, "empty");
    expect(getByText("No entries in 2026-02.")).toBeTruthy();
  });

  it("failed: the request rejects", async () => {
    const { container } = mount(stub({ "GET /api/me": () => Promise.reject(new TypeError("network down")) }));
    await expectState(container, "failed");
  });

  it("failed: the request times out", async () => {
    const { container } = mount(stub({ [`GET /api/households/${HOUSEHOLD}/summary`]: hang }), 20);
    await expectState(container, "failed");
  });

  it("failed: the server answers 500", async () => {
    const { container } = mount(stub({ [`GET /api/households/${HOUSEHOLD}/summary`]: () => reply(500) }));
    await expectState(container, "failed");
  });

  it("unauthenticated: 401", async () => {
    const { container } = mount(stub({ "GET /api/me": () => reply(401) }));
    await expectState(container, "unauthenticated");
  });

  it("disabled_503: the server is up but cannot serve", async () => {
    const { container } = mount(stub({ "GET /api/me": () => reply(503) }));
    await expectState(container, "disabled_503");
  });

  it("not_composed: the route is not on this server", async () => {
    const { container } = mount(stub({ "GET /api/me": () => reply(404) }));
    await expectState(container, "not_composed");
  });

  it("partial: the total loaded, the entries did not", async () => {
    const { container, getByText } = mount(stub({ [`GET /api/households/${HOUSEHOLD}/entries`]: () => reply(500) }));
    await expectState(container, "partial");
    expect(getByText("60.24")).toBeTruthy();
  });

  it("write_failed: adding an entry fails and says so", async () => {
    const { container, getByText } = mount(stub({ [`POST /api/households/${HOUSEHOLD}/entries`]: () => reply(500) }));
    await expectState(container, "loaded");
    const amount = container.querySelector('[data-control="summary.amount"]');
    const add = container.querySelector('[data-control="summary.add"]');
    if (amount === null || add === null) throw new Error("the add-entry controls are missing");
    fireEvent.change(amount, { target: { value: "100" } });
    fireEvent.click(add);
    await expectState(container, "write_failed");
    expect(getByText(/The entry was not saved/)).toBeTruthy();
  });

  it("produced every ScreenState in contracts/registry.py (runs last)", () => {
    expect([...produced].sort()).toEqual([...SCREEN_STATES].sort());
  });
});
