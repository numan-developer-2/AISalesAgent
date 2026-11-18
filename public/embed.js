/* Systematic embeddable assistant. No private credentials belong in this file. */
(() => {
  const script = document.currentScript;
  if (!script || document.getElementById("systematic-assistant-frame")) return;
  const base = new URL(script.src).origin;
  const business = script.dataset.business || "systematic";
  fetch(base + "/api/public/config/" + encodeURIComponent(business), {
    credentials: "omit",
  })
    .then((r) => {
      if (!r.ok) throw new Error("Assistant unavailable");
      return r.json();
    })
    .then((config) => {
      if (!config.allowed_origins.includes(location.origin)) return;
      const launcher = document.createElement("button");
      launcher.textContent = "Chat with " + config.short_name;
      launcher.setAttribute("aria-expanded", "false");
      launcher.setAttribute("aria-controls", "systematic-assistant-frame");
      Object.assign(launcher.style, {
        position: "fixed",
        bottom: "24px",
        right: "24px",
        zIndex: "2147483000",
        padding: "15px 22px",
        border: "0",
        borderRadius: "30px",
        background: config.accent,
        color: "#fff",
        font: "600 14px system-ui",
        cursor: "pointer",
        boxShadow: "0 6px 25px #0002",
      });
      const frame = document.createElement("iframe");
      frame.id = "systematic-assistant-frame";
      frame.title = config.name + " sales assistant";
      const source = new URL(location.origin + location.pathname);
      const query = new URLSearchParams(location.search);
      for (const key of ["utm_source", "utm_medium", "utm_campaign"]) {
        const value = query.get(key);
        if (value && /^[\w .-]{1,80}$/.test(value))
          source.searchParams.set(key, value);
      }
      frame.src =
        base +
        "/widget?business=" +
        encodeURIComponent(business) +
        "&source_page=" +
        encodeURIComponent(source.href.slice(0, 1000));
      frame.setAttribute(
        "sandbox",
        "allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox",
      );
      Object.assign(frame.style, {
        display: "none",
        position: "fixed",
        bottom: "85px",
        right: "24px",
        width: "min(420px, calc(100vw - 32px))",
        height: "min(700px, calc(100dvh - 120px))",
        border: "0",
        borderRadius: "18px",
        boxShadow: "0 15px 70px #0003",
        zIndex: "2147483000",
        background: "white",
      });
      launcher.onclick = () => {
        const opening = frame.style.display === "none";
        frame.style.display = opening ? "block" : "none";
        launcher.setAttribute("aria-expanded", String(opening));
        launcher.textContent = opening
          ? "Close assistant"
          : "Chat with " + config.short_name;
        if (opening) frame.focus();
      };
      window.addEventListener("message", (event) => {
        if (
          event.origin !== base ||
          event.source !== frame.contentWindow ||
          event.data?.business !== business
        )
          return;
        if (
          event.data.type === "systematic:navigate" &&
          config.navigation.some((n) => n.url === event.data.url)
        )
          location.assign(event.data.url);
      });
      document.body.append(frame, launcher);
    })
    .catch(() => {
      /* A unavailable assistant must not break its host website. */
    });
})();
