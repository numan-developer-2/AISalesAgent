import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { Widget, DemoSite } from "./Widget";
import "./styles.css";
import "./analytics.css";
import { SHOWCASE } from "./showcase/mode";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="empty">
        <h1>Let's reconnect.</h1>
        <p>The workspace encountered an unexpected error.</p>
        <button className="button primary" onClick={() => location.reload()}>
          Reload workspace
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
const path = SHOWCASE
  ? "/" + (new URLSearchParams(location.search).get("view") || "workspace")
  : location.pathname;
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      {path === "/widget" ? (
        <Widget />
      ) : path === "/demo" ? (
        <DemoSite />
      ) : (
        <App />
      )}
    </ErrorBoundary>
  </React.StrictMode>,
);
