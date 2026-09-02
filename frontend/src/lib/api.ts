/**
 * Typed API client.
 *
 * One place owns the access token, the Authorization header, and the refresh
 * dance. A 401 triggers a single refresh attempt and one retry; concurrent
 * requests share that attempt rather than each firing their own, which is how
 * a refresh endpoint ends up rate-limited by its own frontend.
 */
import type {
  Adherence, CaseloadRow, CursorPage, ExerciseSession, Plan, RiskFlag,
  Symptom, TokenPair, User, PatientProfile, Vitals,
} from "./types";

const BASE = "/api/v1";
const ACCESS_KEY = "cr.access";
const REFRESH_KEY = "cr.refresh";

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

export const tokenStore = {
  get access() { return localStorage.getItem(ACCESS_KEY); },
  get refresh() { return localStorage.getItem(REFRESH_KEY); },
  set(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;      // share one attempt
  const token = tokenStore.refresh;
  if (!token) return false;

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!res.ok) { tokenStore.clear(); return false; }
      tokenStore.set(await res.json());
      return true;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const access = tokenStore.access;
  if (access) headers.set("Authorization", `Bearer ${access}`);

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401 && retry && tokenStore.refresh) {
    if (await tryRefresh()) return request<T>(path, options, false);
  }

  if (!res.ok) {
    let detail: unknown;
    let message = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail;
      message =
        typeof body.detail === "string"
          ? body.detail
          // FastAPI validation errors arrive as an array; surface the first.
          : Array.isArray(body.detail) && body.detail[0]?.msg
            ? body.detail[0].msg
            : message;
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, message, detail);
  }

  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const get = <T>(p: string) => request<T>(p);
const post = <T>(p: string, body: unknown) =>
  request<T>(p, { method: "POST", body: JSON.stringify(body) });
const patch = <T>(p: string, body: unknown) =>
  request<T>(p, { method: "PATCH", body: JSON.stringify(body) });

export const api = {
  auth: {
    login: (email: string, password: string) =>
      post<TokenPair>("/auth/login", { email, password }),
    register: (email: string, password: string, full_name: string) =>
      post<TokenPair>("/auth/register", { email, password, full_name }),
    me: () => get<{ user: User; patient_profile: PatientProfile | null }>("/auth/me"),
  },
  vitals: {
    list: (limit = 30, cursor?: string) =>
      get<CursorPage<Vitals>>(`/vitals?limit=${limit}${cursor ? `&cursor=${cursor}` : ""}`),
    create: (body: Partial<Vitals>) =>
      post<{ vitals: Vitals; flags_raised: RiskFlag[] }>("/vitals", body),
  },
  symptoms: {
    list: (limit = 20) => get<CursorPage<Symptom>>(`/symptoms?limit=${limit}`),
    create: (description: string, severity: string) =>
      post<{ symptom: Symptom; flags_raised: RiskFlag[] }>("/symptoms", { description, severity }),
  },
  program: {
    activePlan: () => get<Plan | null>("/plans/active"),
    sessions: (limit = 20) => get<CursorPage<ExerciseSession>>(`/sessions?limit=${limit}`),
    logSession: (body: Partial<ExerciseSession>) =>
      post<{ session: ExerciseSession; flags_raised: RiskFlag[] }>("/sessions", body),
    adherence: (windowDays = 28) => get<Adherence>(`/adherence?window_days=${windowDays}`),
    prescribe: (patientId: string, body: Partial<Plan>) =>
      post<Plan>(`/patients/${patientId}/plans`, body),
  },
  clinician: {
    caseload: (windowDays = 28) =>
      get<{ window_days: number; patients: CaseloadRow[] }>(
        `/clinician/caseload?window_days=${windowDays}`,
      ),
    flags: (status = "open", limit = 50) =>
      get<CursorPage<RiskFlag>>(`/clinician/flags?status=${status}&limit=${limit}`),
    resolveFlag: (id: string, status: string, note?: string) =>
      patch<RiskFlag>(`/clinician/flags/${id}`, { status, resolution_note: note }),
    patientVitals: (patientId: string, limit = 30) =>
      get<CursorPage<Vitals>>(`/clinician/patients/${patientId}/vitals?limit=${limit}`),
    patientSymptoms: (patientId: string, limit = 20) =>
      get<CursorPage<Symptom>>(`/clinician/patients/${patientId}/symptoms?limit=${limit}`),
  },
};
