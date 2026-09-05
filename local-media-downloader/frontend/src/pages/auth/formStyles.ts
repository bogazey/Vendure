// Re-exports of the shared Loady glass/gradient tokens (see
// src/styles/ui.ts), kept under the original names so every auth page's
// existing imports keep working untouched.
import { glassInput, glassPanel, primaryButton } from "../../styles/ui";

export const inputClass = glassInput;
export const authCardClass = `auth-card flex flex-col gap-5 p-6 sm:p-8 ${glassPanel}`;
export const primaryButtonClass = `${primaryButton} w-full`;
