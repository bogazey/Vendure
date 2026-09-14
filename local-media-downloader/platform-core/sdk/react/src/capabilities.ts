import type { Capabilities } from "./types";

/** Mirrors `platform_client.PlatformClient.has_capability` on the Python
 * side exactly, so a capability check gives the same answer whether it
 * runs in a product's backend or its frontend. Deliberately dumb: it does
 * not call the network, and treats a missing key as false (fail closed).
 * `-1` is the `UNLIMITED` sentinel from `capability_service.py` and always
 * satisfies `atLeast`. */
export function hasCapability(capabilities: Capabilities | null | undefined, key: string, atLeast?: number): boolean {
  if (!capabilities || !(key in capabilities)) return false;
  const value = capabilities[key];
  if (typeof value === "boolean") return value;
  if (atLeast !== undefined && typeof value === "number") return value === -1 || value >= atLeast;
  return Boolean(value);
}
