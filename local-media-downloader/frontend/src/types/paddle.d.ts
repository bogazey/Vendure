/**
 * Minimal ambient types for Paddle.js v2 (Paddle Billing) - only the shape
 * this app actually uses. Paddle.js itself is never bundled; it's loaded
 * from Paddle's own CDN at runtime (see lib/paddle.ts) so there is nothing
 * to keep in sync with a real npm package here.
 */
interface PaddleCheckoutOpenOptions {
  items: { priceId: string; quantity: number }[];
  customData?: Record<string, unknown>;
  customer?: { email?: string };
}

interface PaddleEventData {
  name: string;
  [key: string]: unknown;
}

interface PaddleStatic {
  Environment: {
    set: (environment: "sandbox" | "production") => void;
  };
  Initialize: (options: { token: string; eventCallback?: (event: PaddleEventData) => void }) => void;
  Checkout: {
    open: (options: PaddleCheckoutOpenOptions) => void;
  };
}

interface Window {
  Paddle?: PaddleStatic;
}
