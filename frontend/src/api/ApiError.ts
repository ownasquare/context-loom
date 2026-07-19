interface ApiErrorOptions {
  status: number;
  code: string;
  message: string;
  requestId?: string;
  details?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor(options: ApiErrorOptions) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.details = options.details;
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    let body: unknown;

    try {
      body = await response.json();
    } catch {
      body = undefined;
    }

    const responseRecord = isErrorRecord(body) ? body : undefined;
    const nestedError = isErrorRecord(responseRecord?.error) ? responseRecord.error : undefined;
    const record = nestedError ?? responseRecord;
    const message = readString(record, "message") ?? readString(record, "detail") ?? response.statusText;

    return new ApiError({
      status: response.status,
      code: readString(record, "code") ?? `http_${response.status}`,
      message: message || "Context Loom could not complete the request.",
      requestId: response.headers.get("x-request-id") ?? readString(record, "request_id"),
      details: record?.details,
    });
  }
}

function isErrorRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function readString(record: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = record?.[key];
  return typeof value === "string" ? value : undefined;
}
