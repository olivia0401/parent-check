import assert from "node:assert/strict";
import test from "node:test";
import { checkMessage, parseCheckResponse } from "../lib/api";
import { result } from "./fixture";

test("the actual backend array contract is validated", () => {
  assert.deepEqual(parseCheckResponse(result), result);
  assert.throws(() => parseCheckResponse({ ...result, advice: "text" }));
  assert.throws(() => parseCheckResponse({ ...result, risk: "SAFE" }));
  assert.throws(() => parseCheckResponse(null));
});

test("a successful HTTP response is checked before being rendered", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ ...result, advice: "wrong" })));
  await assert.rejects(checkMessage({ content: "hello", source: "other", lang: "en" }), /Invalid analysis response/);
});

test("unavailable infrastructure is explained without internal error codes", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ error: "rate_limiter_unavailable" }), { status: 503 }));
  await assert.rejects(checkMessage({ content: "hello", source: "other", lang: "zh" }), (error: Error) => {
    assert.match(error.message, /稍后重试/);
    assert.doesNotMatch(error.message, /rate_limiter/);
    return true;
  });
});
