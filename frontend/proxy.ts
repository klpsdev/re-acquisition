import { NextResponse, type NextRequest } from "next/server";

/**
 * Runs before every request.
 *
 * 1. Password gate: when SITE_USERNAME and SITE_PASSWORD are set, the browser
 *    asks for them before showing anything (HTTP basic auth).
 * 2. API token: when API_TOKEN is set, it's attached to every /api/* request
 *    that Next.js forwards to FastAPI, so the API only answers this app.
 *    The token never reaches the browser.
 */
export function proxy(req: NextRequest) {
  const user = process.env.SITE_USERNAME;
  const pass = process.env.SITE_PASSWORD;

  if (user && pass) {
    const header = req.headers.get("authorization") ?? "";
    const [scheme, encoded] = header.split(" ");
    let ok = false;
    if (scheme === "Basic" && encoded) {
      const decoded = atob(encoded);
      const i = decoded.indexOf(":");
      ok = decoded.slice(0, i) === user && decoded.slice(i + 1) === pass;
    }
    if (!ok) {
      return new NextResponse("Sign in required", {
        status: 401,
        headers: { "WWW-Authenticate": 'Basic realm="SPREV Acquisition Engine", charset="UTF-8"' },
      });
    }
  }

  const token = process.env.API_TOKEN;
  if (token && req.nextUrl.pathname.startsWith("/api/")) {
    const headers = new Headers(req.headers);
    headers.delete("authorization"); // don't forward the site password to the API
    headers.set("x-api-token", token);
    return NextResponse.next({ request: { headers } });
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
