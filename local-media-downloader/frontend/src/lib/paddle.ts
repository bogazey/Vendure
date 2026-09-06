/**
 * Paddle.js v2 loader + checkout helper.
 *
 * The backend never hands the frontend anything but a price_id and the
 * PUBLIC client-side token (see /api/billing/checkout) - Paddle's actual
 * checkout UI runs entirely client-side against that. The backend's real
 * API key never reaches this file or the bundle it ends up in.
 *
 * A successful checkout here is NOT the source of truth for a plan change -
 * that's the /api/billing/paddle/webhook handler (see COMMERCIAL_ARCHITECTURE.md
 * §5). This module's job ends at opening Paddle's overlay and reporting
 * back when the user completes or closes it, nothing more.
 */
import type { CheckoutResponse } from "../types/commercial";
import { track } from "./analytics";

const PADDLE_JS_URL = "https://cdn.paddle.com/paddle/v2/paddle.js";

let scriptLoadPromise: Promise<void> | null = null;
let initializedToken: string | null = null;
// Paddle.js registers exactly one global eventCallback at Initialize time,
// but each checkout needs its own "what happens when this one finishes"
// handler - this indirection lets openPaddleCheckout swap that in per call
// without re-initializing Paddle (which would drop the overlay if already open).
let currentEventHandler: ((event: PaddleEventData) => void) | null = null;

function loadPaddleScript(): Promise<void> {
  if (window.Paddle) return Promise.resolve();
  if (scriptLoadPromise) return scriptLoadPromise;

  scriptLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = PADDLE_JS_URL;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load Paddle.js"));
    document.head.appendChild(script);
  });
  return scriptLoadPromise;
}

async function ensurePaddleInitialized(clientToken: string, environment: string): Promise<void> {
  await loadPaddleScript();
  if (!window.Paddle) throw new Error("Paddle.js did not initialize correctly.");
  if (initializedToken === clientToken) return;

  if (environment === "sandbox") {
    window.Paddle.Environment.set("sandbox");
  }
  window.Paddle.Initialize({
    token: clientToken,
    eventCallback: (event) => {
      if (event.name === "checkout.completed") track("subscription_activated");
      currentEventHandler?.(event);
    },
  });
  initializedToken = clientToken;
}

/**
 * Opens Paddle's hosted checkout overlay for the given price. Resolves once
 * the overlay has been asked to open - it does NOT wait for the purchase to
 * complete. `onEvent` receives Paddle's checkout.* events (completed,
 * closed, ...) for THIS specific checkout so the caller can, e.g., refresh
 * the account once the user finishes - though per COMMERCIAL_ARCHITECTURE.md
 * §5, the account's plan itself only actually changes once the webhook
 * lands, not from this event alone.
 */
export async function openPaddleCheckout(
  checkout: CheckoutResponse,
  onEvent?: (event: PaddleEventData) => void
): Promise<void> {
  await ensurePaddleInitialized(checkout.client_token, checkout.environment);
  currentEventHandler = onEvent ?? null;
  window.Paddle!.Checkout.open({
    items: [{ priceId: checkout.price_id, quantity: 1 }],
    customData: checkout.custom_data,
  });
}

/** Secure provider overlay for an existing subscription, without a new purchase. */
export async function openPaymentUpdate(
  checkout: import("../types/commercial").PaymentCheckout,
  onEvent?: (event: PaddleEventData) => void
): Promise<void> {
  await ensurePaddleInitialized(checkout.client_token, checkout.environment);
  currentEventHandler = onEvent ?? null;
  window.Paddle!.Checkout.open({ transactionId: checkout.transaction_id });
}
