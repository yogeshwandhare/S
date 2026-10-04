import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { stripTypeScriptTypes } from "node:module";
import test from "node:test";

const source = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const code = stripTypeScriptTypes(source.replace("import.meta.env.VITE_API_BASE_URL", '""'));
let moduleId = 0;
const loadApi = () => import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}#${moduleId++}`);
const json = (body, status = 200) => Response.json(body, { status });

test("validation errors display field messages rather than object strings", async (t) => {
  const { api } = await loadApi();
  t.mock.method(globalThis, "fetch", async () => json({ detail: [
    { loc: ["body", "source_uri"], msg: "Select HTTP / MJPEG stream", input: "private-url" },
    { loc: ["body", "name"], msg: "Name is required" },
  ] }, 422));
  await assert.rejects(api.post("/api/cameras", {}), {
    status: 422, message: "source_uri: Select HTTP / MJPEG stream; name: Name is required",
  });
});

test("unknown error objects use a readable fallback", async (t) => {
  const { api } = await loadApi();
  t.mock.method(globalThis, "fetch", async () => json({ detail: { unexpected: true } }, 500));
  await assert.rejects(api.get("/api/cameras"), { message: "Request failed with status 500" });
});

test("plain API error messages are preserved", async (t) => {
  const { api } = await loadApi();
  t.mock.method(globalThis, "fetch", async () => json({ detail: "Camera not found" }, 404));
  await assert.rejects(api.get("/api/cameras/missing"), { message: "Camera not found" });
});

test("expired access cookie refreshes and retries camera creation with the same body", async (t) => {
  const { api } = await loadApi();
  const calls = [];
  t.mock.method(globalThis, "fetch", async (path, options) => {
    calls.push({ path, options });
    if (calls.length === 1) return json({ detail: "Not authenticated" }, 401);
    if (path === "/api/auth/refresh") return json({ id: "user" });
    return json({ id: "camera" }, 201);
  });
  assert.deepEqual(await api.post("/api/cameras", { name: "Entrance" }), { id: "camera" });
  assert.deepEqual(calls.map((call) => call.path), ["/api/cameras", "/api/auth/refresh", "/api/cameras"]);
  assert.deepEqual(calls[0].options, calls[2].options);
  assert.ok(calls.every((call) => call.options.credentials === "include"));
});

test("concurrent failures share one refresh request", async (t) => {
  const { api } = await loadApi();
  let refreshed = false;
  let refreshCount = 0;
  t.mock.method(globalThis, "fetch", async (path) => {
    if (path === "/api/auth/refresh") {
      refreshCount++;
      await new Promise((resolve) => setTimeout(resolve, 10));
      refreshed = true;
      return json({ id: "user" });
    }
    return refreshed ? json([]) : json({}, 401);
  });
  await Promise.all([api.get("/api/cameras"), api.get("/api/models")]);
  assert.equal(refreshCount, 1);
});

test("rejected refresh reports session expiry without retrying the mutation", async (t) => {
  const { api, onSessionExpired } = await loadApi();
  let expired = 0;
  onSessionExpired(() => expired++);
  const fetch = t.mock.method(globalThis, "fetch", async () => json({}, 401));
  await assert.rejects(api.post("/api/cameras", {}), { status: 401 });
  assert.equal(fetch.mock.callCount(), 2);
  assert.equal(expired, 1);
});

test("a retry that still returns 401 expires the session without a refresh loop", async (t) => {
  const { api, onSessionExpired } = await loadApi();
  let expired = 0;
  onSessionExpired(() => expired++);
  const fetch = t.mock.method(globalThis, "fetch", async (path) =>
    path === "/api/auth/refresh" ? json({}) : json({}, 401));
  await assert.rejects(api.get("/api/auth/me"), { status: 401 });
  assert.equal(fetch.mock.callCount(), 3);
  assert.equal(expired, 1);
});

test("invalid login and forbidden requests do not refresh or expire the session", async (t) => {
  const { api, onSessionExpired } = await loadApi();
  let expired = 0;
  onSessionExpired(() => expired++);
  const fetch = t.mock.method(globalThis, "fetch", async (path) =>
    json({}, path === "/api/auth/login" ? 401 : 403));
  await assert.rejects(api.post("/api/auth/login", {}), { status: 401 });
  await assert.rejects(api.post("/api/cameras", {}), { status: 403 });
  assert.equal(fetch.mock.callCount(), 2);
  assert.equal(expired, 0);
});

test("temporary refresh failures preserve the session", async (t) => {
  const { api, onSessionExpired } = await loadApi();
  let expired = 0;
  onSessionExpired(() => expired++);
  t.mock.method(globalThis, "fetch", async (path) =>
    json({}, path === "/api/auth/refresh" ? 503 : 401));
  await assert.rejects(api.get("/api/cameras"), { status: 503 });
  assert.equal(expired, 0);
});
