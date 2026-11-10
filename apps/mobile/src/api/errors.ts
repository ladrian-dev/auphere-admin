/**
 * An answer from the API that is not a success, with the closed-vocabulary
 * `code` the screen turns into a sentence (constitution §III: the sentence
 * lives in the app, never in the backend). `status` 0 is «no network».
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly info: Record<string, unknown>;

  constructor(status: number, code: string | null, info: Record<string, unknown> = {}) {
    super(code ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.info = info;
  }

  get offline(): boolean {
    return this.status === 0;
  }
}

/**
 * FastAPI's `{"detail": {"code": …}}`, `{"detail": "…"}` or a 422 list → code
 * + info. The public `/app/*` routes answer `{"code": …}` at the top level.
 */
export function errorOf(status: number, body: unknown): ApiError {
  if (body && typeof body === "object" && !("detail" in body) && typeof (body as { code?: unknown }).code === "string") {
    const info = body as Record<string, unknown>;
    return new ApiError(status, info.code as string, info);
  }
  const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const info = detail as Record<string, unknown>;
    return new ApiError(status, typeof info.code === "string" ? info.code : null, info);
  }
  return new ApiError(status, typeof detail === "string" ? detail : null);
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}
