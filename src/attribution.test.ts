import { expect, it } from "vitest";
import { sourcePage } from "./attribution";

it("captures approved campaign tags without forwarding unrelated URL data", () => {
  history.replaceState(
    {},
    "",
    "/widget?source_page=" +
      encodeURIComponent(
        "https://example.com/seo?utm_source=google&utm_medium=cpc&utm_campaign=autumn&token=private&email=person@example.com#fragment",
      ),
  );
  const source = new URL(sourcePage());
  expect(source.origin + source.pathname).toBe("https://example.com/seo");
  expect([...source.searchParams.keys()]).toEqual([
    "utm_source",
    "utm_medium",
    "utm_campaign",
  ]);
  expect(source.hash).toBe("");
});

it("drops email-like campaign values and handles malformed source URLs", () => {
  history.replaceState(
    {},
    "",
    "/widget?source_page=" +
      encodeURIComponent("https://example.com/?utm_source=person@example.com"),
  );
  expect(new URL(sourcePage()).search).toBe("");
  history.replaceState({}, "", "/widget?source_page=not-a-url");
  expect(sourcePage()).toBe("");
});
