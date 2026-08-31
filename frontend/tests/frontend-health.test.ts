import { describe, expect, it } from "vitest";
import { GET } from "@/app/healthz/route";

describe("frontend production health route", () => {
  it("returns a bounded runtime liveness response without configuration data", async () => {
    const response = GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ status: "ok", service: "frontend" });
  });
});
