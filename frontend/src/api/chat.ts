// Typed client for the chatbot + conversations API.
// In dev, Vite proxies /api to the FastAPI backend; in production FastAPI serves
// this SPA, so the relative /api path works in both.

import { authFetch } from '../auth/oidc';

// ── stable per-browser client id (identity until real auth exists) ────────────
const CLIENT_KEY = 'ntt.clientId';
export function getClientId(): string {
  let id = localStorage.getItem(CLIENT_KEY);
  if (!id) {
    id = (crypto.randomUUID?.() ?? `c-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    localStorage.setItem(CLIENT_KEY, id);
  }
  return id;
}

// The active conversation is remembered per-browser so a reload / new tab
// restores the same thread.
const ACTIVE_KEY = 'ntt.activeConversationId';
export const getActiveConversationId = () => localStorage.getItem(ACTIVE_KEY);
export const setActiveConversationId = (id: string | null) =>
  id ? localStorage.setItem(ACTIVE_KEY, id) : localStorage.removeItem(ACTIVE_KEY);

function headers(): HeadersInit {
  // X-Client-Id is still sent so the app works with AUTH_DISABLED=1 (local dev
  // and the test suite). With auth on, the backend ignores it in favour of the
  // verified token subject — it cannot be used to act as another user.
  return { 'Content-Type': 'application/json', 'X-Client-Id': getClientId() };
}

/**
 * `fetch` for our API: attaches the bearer token when signed in, and retries
 * once after a refresh on 401.
 *
 * Every call below goes through this rather than raw `fetch`, so authentication
 * is one seam instead of a decision repeated at twenty call sites — the same
 * reason the backend declares auth at the router.
 */
async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  return authFetch(input, { ...init, headers: { ...headers(), ...(init.headers ?? {}) } });
}

// ── types ─────────────────────────────────────────────────────────────────────

// The solution type of a single resolution step. One report legitimately mixes
// several of these in sequence (e.g. extract with SQL, then run a script).
export type ActionType =
  | 'SQL_QUERY' | 'CODE' | 'CONFIG_CHANGE' | 'INFRA_ACTION'
  | 'INVESTIGATION_MEDIA' | 'LOG_ANALYSIS' | 'MANUAL_PROCEDURE' | 'DOC_REFERENCE';

export interface ResolutionStep {
  step: number;
  action_type?: ActionType;
  title: string;
  purpose?: string;
  action: string;
  validation?: string;
  evidence?: string[];
  artifact?: { language: string; title: string; content: string } | null;
  // Irreversible operations detected in this step (server-side, see
  // backend/app/chatbot/hazard.py). `hazard_ungrounded` means no report
  // documents it — the model proposed it from general knowledge.
  hazard?: string[];
  hazard_ungrounded?: boolean;
}

export interface SourceLink {
  incident_id: string | null;
  title: string | null;
  source: string | null;
  filename: string | null;
  open_url: string | null; // in-app route to open the cited report
  score: number | null;
}

export interface Artifact {
  language: string;   // sql, bash, python, java, yaml, ... drives syntax highlighting
  title: string;
  content: string;
}

export interface ChatAnswer {
  answer: string;
  incident_type: string;
  confidence: number;
  low_confidence: boolean;
  steps: ResolutionStep[];
  artifacts: Artifact[];          // typed supporting artifacts (not SQL-only)
  supporting_sql: string[];       // legacy, kept for backward compatibility
  matched_report_ids: string[];
  retrieval: SourceLink[];
  raw: string;
  is_chat: boolean;               // greeting/smalltalk reply, not an incident
  needs_clarification?: boolean;  // too vague / insufficient evidence to diagnose
  security_note?: string | null;  // set when prompt-injection was detected
  // Report sections rendered in order: Problem Summary (answer) / Root Cause /
  // Investigation / Resolution Steps / Validation / Additional Notes.
  root_cause?: string;
  investigation?: string;
  validation?: string;
  additional_notes?: string;
  hazards?: string[];
  has_hazard?: boolean;
  hazard_ungrounded?: boolean;
  has_media?: boolean;                 // source report includes screenshots
  no_documented_resolution?: boolean;
  ai_suggestion?: string;              // shown marked as AI-suggested
  refused?: boolean;
}

export interface ChatResponse {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  answer: ChatAnswer;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  pinned?: boolean;
}

export interface StoredMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
  has_image: boolean;
  payload: (ChatAnswer & { links?: string[] }) | { links?: string[] } | null;
  feedback: number | null;
  created_at: number;
}

// ── calls ─────────────────────────────────────────────────────────────────────

async function json<T>(res: Response): Promise<T> {
  if (res.status === 503) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || 'The chatbot is currently unavailable.');
  }
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function sendChat(
  query: string,
  opts: { imageB64?: string | null; conversationId?: string | null; links?: string[] } = {},
): Promise<ChatResponse> {
  const res = await apiFetch('/api/chat', {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({
      query,
      image_b64: opts.imageB64 ?? null,
      conversation_id: opts.conversationId ?? null,
      links: opts.links ?? [],
    }),
  });
  return json<ChatResponse>(res);
}

// Streaming chat over SSE. Invokes callbacks as events arrive:
//   onMeta(conversationId)  — sent first (needed for a fresh conversation)
//   onToken(text)           — incremental LLM output (append to a live bubble)
//   onChat(text)            — a greeting/smalltalk reply (whole text at once)
//   onDone(answer)          — the final structured answer
export interface StreamHandlers {
  onMeta?: (conversationId: string) => void;
  onToken?: (text: string) => void;
  onChat?: (text: string) => void;
  onDone?: (answer: ChatAnswer, assistantMessageId: string) => void;
  onError?: (detail: string) => void;
}

export async function streamChat(
  query: string,
  opts: { imageB64?: string | null; conversationId?: string | null; links?: string[] } = {},
  h: StreamHandlers = {},
): Promise<void> {
  const res = await apiFetch('/api/chat/stream', {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({
      query,
      image_b64: opts.imageB64 ?? null,
      conversation_id: opts.conversationId ?? null,
      links: opts.links ?? [],
    }),
  });
  if (!res.ok || !res.body) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `Request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line.
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      const ev = JSON.parse(line.slice(6));
      if (ev.type === 'meta') h.onMeta?.(ev.conversation_id);
      else if (ev.type === 'token') h.onToken?.(ev.text);
      else if (ev.type === 'chat') h.onChat?.(ev.text);
      else if (ev.type === 'done') h.onDone?.(ev.answer, ev.assistant_message_id);
      else if (ev.type === 'error') h.onError?.(ev.detail);
    }
  }
}

export async function listConversations(): Promise<Conversation[]> {
  return json(await apiFetch('/api/conversations'));
}

export async function listMessages(conversationId: string): Promise<StoredMessage[]> {
  return json(await apiFetch(`/api/conversations/${conversationId}/messages`));
}

export async function renameConversation(id: string, title: string): Promise<void> {
  await json(await apiFetch(`/api/conversations/${id}`, {
    method: 'PATCH', body: JSON.stringify({ title }),
  }));
}

// Pin a conversation to the top of the sidebar. Returns false when the backend
// has no pinning support (the SQLite fallback answers 501), so the caller can
// hide the control instead of surfacing an error the user cannot act on.
export async function pinConversation(id: string, pinned: boolean): Promise<boolean> {
  const res = await apiFetch(`/api/conversations/${id}/pin`, {
    method: 'POST', body: JSON.stringify({ pinned }),
  });
  if (res.status === 501) return false;
  await json(res);
  return true;
}

// ── profile ───────────────────────────────────────────────────────────────────

export interface Profile {
  display_name: string;
  avatar_url: string;
}

export async function getProfile(): Promise<Profile> {
  return json(await apiFetch('/api/profile'));
}

export async function updateProfile(patch: Partial<Profile>): Promise<Profile> {
  return json(await apiFetch('/api/profile', {
    method: 'PATCH', body: JSON.stringify(patch),
  }));
}

export async function deleteConversation(id: string): Promise<void> {
  await json(await apiFetch(`/api/conversations/${id}`, { method: 'DELETE' }));
}

// Thumbs feedback on an assistant message (1 up, -1 down, null clears).
export async function sendFeedback(messageId: string, value: 1 | -1 | null): Promise<void> {
  await json(await apiFetch(`/api/messages/${messageId}/feedback`, {
    method: 'POST', body: JSON.stringify({ value }),
  }));
}

// Submit a human correction so future similar questions use it.
export async function sendCorrection(question: string, correction: string): Promise<void> {
  await json(await apiFetch('/api/corrections', {
    method: 'POST', body: JSON.stringify({ question, correction }),
  }));
}

// Turn a diagnosed conversation into a saved incident report.
export interface GeneratedReport { success: boolean; jsonFilename: string; report: any }
export async function generateReport(conversationId: string): Promise<GeneratedReport> {
  return json(await apiFetch(`/api/conversations/${conversationId}/report`, {
    method: 'POST',
  }));
}

// Fetch a cited report's JSON (for opening in-app).
export async function fetchReport(openUrl: string): Promise<any> {
  return json(await apiFetch(openUrl));
}

// ── search ────────────────────────────────────────────────────────────────────

// A conversation that matched, with the best snippet from it. `matched_by`
// reports which arm found it — useful for explaining a result that shares no
// words with the query (it was the semantic arm).
export interface ConversationHit {
  conversation_id: string;
  title: string;
  snippet: string;          // contains <mark> tags from ts_headline
  matched_by: 'keyword' | 'semantic' | 'both';
  score: number;
  hit_count: number;
  best_message_id: string;
  created_at: number;
}

export interface MessageHit {
  message_id: string;
  conversation_id: string;
  conversation_title: string;
  role: string;
  text: string;
  snippet: string;
  created_at: number;
  score: number;
  matched_by: 'keyword' | 'semantic' | 'both';
}

export interface SearchResponse<T> {
  query: string;
  results: T[];
  grouped: boolean;
  available: boolean;       // false when the backend has no search index
}

// Grouped: one entry per conversation, for the sidebar.
export async function searchConversations(
  q: string,
  limit = 20,
): Promise<SearchResponse<ConversationHit>> {
  const params = new URLSearchParams({ q, limit: String(limit), group: 'true' });
  return json(await apiFetch(`/api/search?${params}`));
}

// Flat: individual message hits, for a full-page result list.
export async function searchMessages(
  q: string,
  opts: { limit?: number; conversationId?: string } = {},
): Promise<SearchResponse<MessageHit>> {
  const params = new URLSearchParams({
    q,
    limit: String(opts.limit ?? 20),
    group: 'false',
  });
  if (opts.conversationId) params.set('conversation_id', opts.conversationId);
  return json(await apiFetch(`/api/search?${params}`));
}
