import { SHOWCASE } from "./showcase/mode";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (SHOWCASE) {
    const { showcaseApi } = await import("./showcase/api");
    return showcaseApi<T>(path, options);
  }
  const response = await fetch("/api" + path, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Request": "1",
      ...options.headers,
    },
  });
  const body = await response
    .json()
    .catch(() => ({ detail: "The server returned an unexpected response." }));
  if (!response.ok) {
    const detail = body.detail;
    throw new ApiError(
      response.status,
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((e: { msg: string }) => e.msg).join(". ")
          : "Something went wrong. Please try again.",
    );
  }
  return body as T;
}
export const send = (value: unknown) => JSON.stringify(value);
export const label = (value: string) =>
  value.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
export const dateLabel = (
  value: string,
  opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" },
) => new Date(value).toLocaleDateString("en-US", opts);
export const initials = (name: string) =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0])
    .join("")
    .toUpperCase();
