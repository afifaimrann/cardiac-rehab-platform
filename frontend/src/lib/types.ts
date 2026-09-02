export type Role = "patient" | "clinician" | "admin";
export type Severity = "mild" | "moderate" | "severe";
export type FlagStatus = "open" | "acknowledged" | "resolved";

export interface User {
  id: string; email: string; full_name: string; role: Role;
  is_active: boolean; created_at: string;
}

export interface PatientProfile {
  id: string; user_id: string; clinician_id: string | null;
  date_of_birth: string | null; primary_condition: string | null;
  language: string; resting_hr_baseline: number | null; target_hr_max: number | null;
}

export interface TokenPair {
  access_token: string; refresh_token: string; token_type: string; expires_in: number;
}

export interface Vitals {
  id: string; patient_id: string; recorded_at: string;
  systolic: number | null; diastolic: number | null; heart_rate: number | null;
  spo2: number | null; weight_kg: number | null; note: string | null;
}

export interface RiskFlag {
  id: string; patient_id: string; source_type: string; source_id: string | null;
  rule_code: string; severity: Severity; message: string; status: FlagStatus;
  created_at: string; resolved_at: string | null; resolution_note: string | null;
}

export interface Symptom {
  id: string; patient_id: string; recorded_at: string;
  description: string; severity: Severity;
}

export interface Plan {
  id: string; patient_id: string; title: string; starts_on: string; ends_on: string | null;
  sessions_per_week: number; minutes_per_session: number;
  target_exertion_max: number | null; instructions: string | null;
  is_active: boolean; created_at: string;
}

export interface ExerciseSession {
  id: string; patient_id: string; plan_id: string | null; performed_at: string;
  activity: string; duration_minutes: number; perceived_exertion: number | null;
  completed: boolean; notes: string | null;
}

export interface Adherence {
  patient_id: string; plan_id: string | null; window_days: number;
  sessions_expected: number; sessions_completed: number;
  minutes_expected: number; minutes_completed: number; adherence_pct: number | null;
}

export interface CaseloadRow {
  patient_id: string; full_name: string; email: string;
  primary_condition: string | null; open_flags: number;
  highest_open_severity: Severity | null; last_vitals_at: string | null;
  sessions_completed: number; adherence_pct: number | null;
}

export interface CursorPage<T> { items: T[]; next_cursor: string | null; }
