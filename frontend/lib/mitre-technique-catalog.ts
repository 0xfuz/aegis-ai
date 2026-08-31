/** Display-only, versioned subset. Names never establish mapping authority. */
export const MITRE_TECHNIQUE_CATALOG_VERSION = "enterprise-attack-v14.1-display-subset";
const names: Readonly<Record<string, string>> = Object.freeze({ T1110: "Brute Force", T1078: "Valid Accounts", T1059: "Command and Scripting Interpreter", T1003: "OS Credential Dumping" });
export function mitreTechniqueName(id: string): string | null { return names[id] ?? null; }
