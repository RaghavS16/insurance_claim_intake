import http from "k6/http";
import { check, sleep } from "k6";
export const options = { scenarios: { api: { executor: "constant-vus", vus: 10, duration: "30s" } } };
export default function () {
  const base = __ENV.BASE_URL || "http://localhost:8000";
  const r = http.get(base + "/health");
  check(r, { "health is 200": (x) => x.status === 200 });
  sleep(1);
}
