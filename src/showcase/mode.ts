export const SHOWCASE = import.meta.env.MODE === "showcase";

// Query-based views work on GitHub project Pages without server rewrites.
export function appUrl(
  view: "workspace" | "demo" | "widget" = "workspace",
  business = "systematic",
) {
  return SHOWCASE
    ? `${import.meta.env.BASE_URL}?view=${view}&business=${encodeURIComponent(business)}`
    : `${view === "workspace" ? "/" : "/" + view}${view === "workspace" ? "" : "?business=" + encodeURIComponent(business)}`;
}
