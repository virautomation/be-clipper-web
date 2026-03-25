import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, verifySessionToken } from "@/lib/auth";

const API_BASE_URL = process.env.AUTOCLIPPER_API_BASE_URL;
 
function buildTargetUrl(path: string[], searchParams: URLSearchParams): string {
  if (!API_BASE_URL) {
    throw new Error("AUTOCLIPPER_API_BASE_URL is not configured");
  }

  const normalizedBase = API_BASE_URL.endsWith("/")
    ? API_BASE_URL.slice(0, -1)
    : API_BASE_URL;
  const pathname = path.join("/");
  const qs = searchParams.toString();
  return qs
    ? `${normalizedBase}/${pathname}?${qs}`
    : `${normalizedBase}/${pathname}`;
}

async function proxyRequest(
  request: NextRequest,
  path: string[],
): Promise<NextResponse> {
  try {
    const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
    const session = verifySessionToken(token);
    if (!session) {
      return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
    }

    const targetUrl = buildTargetUrl(path, request.nextUrl.searchParams);

    const forwardedHeaders = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) {
      forwardedHeaders.set("content-type", contentType);
    }

    const init: RequestInit = {
      method: request.method,
      headers: forwardedHeaders,
      cache: "no-store",
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.text();
    }

    const backendResponse = await fetch(targetUrl, init);
    const bodyText = await backendResponse.text();

    return new NextResponse(bodyText, {
      status: backendResponse.status,
      headers: {
        "content-type":
          backendResponse.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : "Proxy request failed";
    return NextResponse.json({ detail }, { status: 500 });
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxyRequest(request, path);
}
