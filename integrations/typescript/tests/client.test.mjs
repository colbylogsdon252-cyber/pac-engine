import test from "node:test";
import assert from "node:assert/strict";
import { PacValidationClient, PacApiError } from "../dist/index.js";

test("read-only validation sends authenticated request and preserves rejected decision", async () => {
  let called = false;
  const transport = async (url, options) => {
    called = true;
    assert.equal(new URL(url).pathname, "/v1/validations");
    assert.equal(options.method, "POST");
    assert.equal(options.headers.Authorization, "Bearer test-token");
    assert.equal(options.redirect, "error");
    return new Response(JSON.stringify({ valid: false, errors: ["blocked"] }), { status: 422 });
  };
  const client = new PacValidationClient("https://pac.example", () => "test-token", transport);
  assert.deepEqual(await client.validate({ action: "test" }), { valid: false, errors: ["blocked"] });
  assert.equal(called, true);
});

test("SDK rejects insecure remote transport", () => {
  assert.throws(() => new PacValidationClient("http://pac.example", () => "token"), /HTTPS/);
});

test("SDK fails closed on malformed response", async () => {
  const client = new PacValidationClient("https://pac.example", () => "token", async () =>
    new Response(JSON.stringify({ ok: true }), { status: 200 }));
  await assert.rejects(client.validate({}), PacApiError);
});

test("SDK fails closed on authentication errors", async () => {
  const client = new PacValidationClient("https://pac.example", () => "token", async () =>
    new Response(JSON.stringify({ valid: false }), { status: 401 }));
  await assert.rejects(client.validate({}), PacApiError);
});
