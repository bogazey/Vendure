import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PlatformAuthProvider } from "@platform-core/react-client";
import App from "./App";

const BACKEND_URL = "http://localhost:9303";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PlatformAuthProvider baseUrl={BACKEND_URL} productId="sample-future-2">
      <App />
    </PlatformAuthProvider>
  </StrictMode>
);
