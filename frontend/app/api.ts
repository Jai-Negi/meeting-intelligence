export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Pulls the plain explanation out of an error response from the backend,
 * which sends it as { "detail": "..." }. Falls back to the given message
 * when the response has no readable explanation.
 */
export async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // the response was not JSON, use the fallback below
  }
  return fallback;
}
