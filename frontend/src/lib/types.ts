export type Role = "patient" | "clinician" | "admin";
export type Severity = "mild" | "moderate" | "severe";
export type FlagStatus = "open" | "acknowledged" | "resolved";

export interface User {
  id: string; email: string; full_name: string; role: Role;
  is_active: boolean; created_at: string;
  /** Path to the stored photograph, or null. Changes whenever the image does. */
  avatar_url: string | null;
}

export interface PatientProfile {
  id: string; user_id: string; clinician_id: string | null;
  date_of_birth: string | null; primary_condition: string | null;
  language: string; resting_hr_baseline: number | null; target_hr_max: number | null;
  height_cm: number | null; sex_at_birth: string | null;
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

export type MessageRole = "user" | "assistant";

export interface Citation {
  index: number; id: string; title: string; source: string; score: number;
}

export interface ChatMessage {
  id: string; conversation_id: string; role: MessageRole; content: string;
  citations: Citation[] | null; transcribed_from_audio: string | null; created_at: string;
}

export interface Conversation {
  id: string; patient_id: string; title: string | null; created_at: string;
}

export interface AskResponse {
  question: ChatMessage;
  answer: ChatMessage;
  citations: Citation[];
  is_emergency: boolean;
  generated: boolean;
  flags_raised: RiskFlag[];
  transcript: string | null;
}

export type WalkTestStatus = "completed" | "stopped_early" | "not_attempted";

export interface WalkTest {
  id: string; patient_id: string; performed_at: string;
  course_length_m: number; laps: number | null; distance_m: number;
  pre_heart_rate: number | null; pre_spo2: number | null;
  pre_borg_dyspnoea: number | null; pre_borg_fatigue: number | null;
  lowest_spo2: number | null; rest_count: number; rest_seconds: number;
  post_heart_rate: number | null; post_spo2: number | null;
  post_borg_dyspnoea: number | null; post_borg_fatigue: number | null;
  status: WalkTestStatus; stop_reason: string | null; symptoms: string | null;
  used_oxygen: boolean; notes: string | null;
  predicted_distance_m: number | null; percent_predicted: number | null;
  below_lower_limit: boolean | null;
}

export interface WalkTestChange {
  previous_distance_m: number; previous_performed_at: string;
  change_m: number; clinically_meaningful: boolean; direction: string;
}

export interface WalkTestResult {
  walk_test: WalkTest;
  change: WalkTestChange | null;
  flags_raised: RiskFlag[];
}

export interface Screening {
  cleared: boolean;
  absolute_blocks: string[];
  relative_cautions: string[];
  summary: string;
}


// --- six-minute walk test prefill -------------------------------------------
export interface PrefillVitals {
  recorded_at: string;
  heart_rate: number | null; systolic: number | null; diastolic: number | null;
  spo2: number | null; weight_kg: number | null;
  /** True when the reading is old enough to retake rather than confirm. */
  stale: boolean;
}

export interface PrefillScreening {
  answered_at: string;
  acs_within_30_days: boolean; unstable_angina: boolean;
  syncope_history: boolean; acute_respiratory_failure: boolean;
}

export interface WalkTestPrefill {
  vitals: PrefillVitals | null;
  weight_kg: number | null; weight_recorded_at: string | null;
  height_cm: number | null; sex_at_birth: string | null; age: number | null;
  course_length_m: number;
  missing_for_prediction: string[];
  previous_screening: PrefillScreening | null;
  previous_distance_m: number | null; previous_performed_at: string | null;
}

// --- appointments -----------------------------------------------------------
export type AppointmentMode = "online" | "in_person";
export type AppointmentStatus = "scheduled" | "completed" | "cancelled" | "no_show";

export interface Slot {
  starts_at: string; ends_at: string;
  mode: AppointmentMode; location: string | null;
  clinician_id: string; clinician_name: string | null;
}

export interface Appointment {
  id: string; patient_id: string; clinician_id: string;
  starts_at: string; ends_at: string;
  mode: AppointmentMode; location: string | null; reason: string | null;
  meeting_provider: string | null; meeting_url: string | null;
  status: AppointmentStatus;
  cancellation_reason: string | null; clinician_notes: string | null;
  clinician_name: string | null; patient_name: string | null;
}

export interface AvailabilityRule {
  id: string; weekday: number; start_time: string; end_time: string;
  slot_minutes: number; mode: AppointmentMode; location: string | null;
  valid_from: string | null; valid_until: string | null; is_active: boolean;
}

// --- direct messages --------------------------------------------------------
export interface DirectMessage {
  id: string; patient_id: string; sender_id: string;
  sender_name: string | null; sender_role: string | null;
  body: string; sent_at: string; read_at: string | null;
}

export interface MessageThread {
  messages: DirectMessage[];
  unread_count: number;
  counterparty_name: string | null;
}

// --- the clinician assistant ------------------------------------------------
export interface AssistantTurn {
  id: string; role: string; content: string;
  tools_used: string | null; created_at: string;
}

export interface AssistantAnswer {
  answer: string; tools_used: string[]; generated: boolean;
}
