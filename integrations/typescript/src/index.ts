/** Read-only PAC validation client. No Proof Token issuance or execution authority. */
export type PacValidationResult = {
  valid: boolean;
  errors?: string[];
  error_classification?: Array<{ code: string; category: string; severity: string; message: string }>;
  message?: string;
  error_type?: string;
};
export class PacApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "PacApiError";
  }
}
export class PacValidationClient {
  constructor(
    private readonly baseUrl: string,
    private readonly getBearerToken: () => Promise<string> | string,
    private readonly transport: typeof fetch = fetch
  ) {
    const url = new URL(baseUrl);
    if (url.protocol !== "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
      throw new Error("PAC remote API requires HTTPS");
    }
  }
  async validate(payload: Record<string, unknown>, signal?: AbortSignal): Promise<PacValidationResult> {
    const token = await this.getBearerToken();
    if (!token || /[\r\n]/.test(token)) throw new Error("Invalid API token");
    const response = await this.transport(new URL("/v1/validations", this.baseUrl), {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
      redirect: "error",
      credentials: "omit"
    });
    const data: unknown = await response.json();
    if (!data || typeof data !== "object" || typeof (data as {valid?: unknown}).valid !== "boolean") {
      throw new PacApiError(response.status, "Malformed PAC validation response");
    }
    if (response.status === 401 || response.status === 503) {
      throw new PacApiError(response.status, "PAC authentication or configuration unavailable");
    }
    if (!response.ok && ![400, 409, 422].includes(response.status)) {
      throw new PacApiError(response.status, "PAC validation request failed");
    }
    return data as PacValidationResult;
  }
}
