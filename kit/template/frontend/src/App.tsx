import { useMemo } from "react";
import { makeApi } from "./gen/client";
import { makeTransport } from "./lib/client";
import { SummaryScreen } from "./screens/summary";

export function App() {
  const api = useMemo(() => makeApi(makeTransport()), []);
  return <SummaryScreen api={api} />;
}
