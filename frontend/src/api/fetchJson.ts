import { ApiError } from "./ApiError";

interface JsonRequestOptions extends Omit<RequestInit, "body" | "headers" | "signal"> {
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
}

export async function fetchJson<T>(
  path: string,
  options: JsonRequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("accept", "application/json");

  if (options.body !== undefined) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(path, {
    ...options,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    headers,
    signal: options.signal,
    credentials: "same-origin",
  });

  if (!response.ok) {
    throw await ApiError.fromResponse(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
