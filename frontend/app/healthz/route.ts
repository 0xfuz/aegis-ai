export const dynamic = "force-dynamic";

/**
 * Public liveness probe for the deployed Next runtime only.
 *
 * It deliberately does not contact the API, workers, Redis, Ollama, or any
 * user-scoped service: optional subsystem state must not make the frontend
 * deployment appear unavailable.
 */
export function GET() {
  return Response.json(
    { status: "ok", service: "frontend" },
    { status: 200, headers: { "Cache-Control": "no-store" } },
  );
}
