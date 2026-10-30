import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import ResultCard from "../components/ResultCard";
import { result } from "./fixture";

test("each advice item is rendered as a separate list entry", () => {
  const html = renderToStaticMarkup(<ResultCard result={result} lang="en" />);
  assert.match(html, /<li[^>]*>Do not transfer money<\/li>/);
  assert.match(html, /<li[^>]*>Do not share codes<\/li>/);
});

test("an empty advice list does not show an empty advice card", () => {
  const html = renderToStaticMarkup(<ResultCard result={{ ...result, advice: [] }} lang="en" />);
  assert.doesNotMatch(html, /What to do now/);
});
