import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { applyTheme, getCachedThemePreference } from "./utils/theme";
import "./index.css";

// Apply the last-known theme before the first paint so there's no flash of
// the wrong theme while the real setting loads from the backend.
applyTheme(getCachedThemePreference());

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
