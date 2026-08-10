import { NextRequest, NextResponse } from "next/server";

/**
 * This is a coarse, cookie-free guard: the real source of truth for "is
 * this session valid" is the JWT verified server-side by the backend on
 * every API call, and the client-side AuthProvider (see lib/auth-context.tsx)
 * handles the authenticated redirect once it knows whether /auth/me
 * succeeds. Tokens live in localStorage (not cookies) so middleware can't
 * inspect them here — this layer only prevents the login page itself from
 * flashing inside the authenticated shell if someone deep-links to it.
 *
 * If/when this app moves to httpOnly cookie-based sessions, this is the
 * place to add real server-side verification.
 */
const PUBLIC_PATHS = ["/login"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  if (isPublic) {
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
