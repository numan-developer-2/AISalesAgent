export function sourcePage() {
  const provided = new URLSearchParams(location.search).get("source_page");
  const source = provided || document.referrer || location.origin + "/demo";
  try {
    const url = new URL(source),
      clean = new URL(url.origin + url.pathname);
    for (const key of ["utm_source", "utm_medium", "utm_campaign"]) {
      const value = url.searchParams.get(key);
      if (value && /^[\w .-]{1,80}$/.test(value))
        clean.searchParams.set(key, value);
    }
    return clean.href.slice(0, 1000);
  } catch {
    return "";
  }
}
