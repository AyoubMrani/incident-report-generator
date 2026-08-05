import React, { useEffect, useRef, useState } from 'react';
import {
  Send, AlertTriangle, Loader2, Database, ImagePlus, X,
  Plus, Trash2, ExternalLink, Link2, FileText, ShieldAlert,
  ThumbsUp, ThumbsDown, Sparkles,
} from 'lucide-react';
import {
  streamChat, listConversations, listMessages, deleteConversation, sendFeedback, sendCorrection,
  generateReport, getActiveConversationId, setActiveConversationId,
  ChatAnswer, SourceLink, Conversation, StoredMessage, ResolutionStep,
} from '../../api/chat';
import { ReportViewer } from '../reports/components/ReportViewer';
import { CodeBlock, splitFencedCode } from './CodeBlock';

// Empty-state prompts. Phrased as real incident symptoms rather than "Tell me
// about X", so clicking one produces a question the retrieval can actually
// ground — and shows a new user what this tool is for.
const SUGGESTIONS = [
  'VPN clients cannot establish a tunnel after the maintenance window',
  'Intermittent DNS resolution failures for internal services',
  'Users are stuck in a redirect loop and cannot sign in',
  'Recurring deadlocks on the orders table during peak traffic',
];

// Render assistant prose, promoting any ```fenced``` code to highlighted blocks.
function RichText({ text }: { text: string }) {
  const segments = splitFencedCode(text);
  return (
    <div className="space-y-2">
      {segments.map((seg, i) =>
        seg.type === 'code'
          ? <CodeBlock key={i} code={seg.content} language={seg.lang} />
          : seg.content.trim() && <p key={i} className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{seg.content.trim()}</p>,
      )}
    </div>
  );
}

// ── local view model ──────────────────────────────────────────────────────────
interface UserMessage { role: 'user'; text: string; hasImage?: boolean; links?: string[] }
interface AssistantMessage { role: 'assistant'; answer: ChatAnswer; messageId?: string; feedback?: number | null }
interface ChatMessage { role: 'chat'; text: string; clarify?: boolean }  // greeting/smalltalk, or a clarification request
interface StreamingMessage { role: 'streaming'; text: string }    // tokens as they arrive
interface ErrorMessage { role: 'error'; text: string }
type Message = UserMessage | AssistantMessage | ChatMessage | StreamingMessage | ErrorMessage;

function confidenceBadge(confidence: number) {
  if (confidence >= 75) return { label: `${confidence}% confidence`, cls: 'bg-green-100 text-green-800' };
  if (confidence >= 50) return { label: `${confidence}% confidence`, cls: 'bg-yellow-100 text-yellow-800' };
  return { label: `${confidence}% confidence`, cls: 'bg-red-100 text-red-800' };
}

// Turn a stored DB message into the local view model (for replay on reload).
function fromStored(m: StoredMessage): Message | null {
  if (m.role === 'assistant' && m.payload && 'incident_type' in m.payload) {
    const answer = m.payload as ChatAnswer;
    // A stored greeting/smalltalk/clarification reply replays as a chat bubble.
    if (answer.is_chat) {
      return { role: 'chat', text: answer.answer || m.text, clarify: answer.needs_clarification };
    }
    return { role: 'assistant', answer, messageId: m.id, feedback: m.feedback };
  }
  if (m.role === 'user') {
    const links = (m.payload && 'links' in m.payload ? m.payload.links : undefined) as string[] | undefined;
    return { role: 'user', text: m.text, hasImage: m.has_image, links };
  }
  if (m.role === 'error') return { role: 'error', text: m.text };
  return null;
}

// Extract external URLs from free text so they render as openable links.
function extractLinks(text: string): string[] {
  const m = text.match(/https?:\/\/[^\s)]+/g);
  return m ? Array.from(new Set(m)) : [];
}

// Replace one message in the list immutably (used for live updates).
function replaceAt(list: Message[], idx: number, msg: Message): Message[] {
  const next = list.slice();
  next[idx] = msg;
  return next;
}

// Flag destructive SQL so the UI can warn before the user runs it.
function isDestructiveSql(sql: string): boolean {
  const s = sql.toUpperCase();
  if (/\b(DROP|TRUNCATE|DELETE)\b/.test(s)) return true;
  // UPDATE without a WHERE clause = full-table write.
  if (/\bUPDATE\b/.test(s) && !/\bWHERE\b/.test(s)) return true;
  return false;
}

// A section carrying no real information — "not documented", "not described",
// or a restatement of nothing — is noise; hide it rather than pad the answer.
function isFiller(text?: string | null): boolean {
  const t = (text || '').trim();
  if (!t) return true;
  return /^(root cause )?not (explicitly )?(documented|described|specified|available)/i.test(t)
    || /^(the )?reports? (do|does) not (describe|document|specify)/i.test(t)
    || /^(no|none|n\/a|unknown)\.?$/i.test(t);
}

// The report an answer is grounded in, shown up front so it is obvious where
// the content came from and the source is one click away.
function SourceCard({ source, onOpen }: {
  source: SourceLink; onOpen: (filename: string) => void;
}) {
  const title = source.title || source.filename || 'source report';
  const openable = !!(source.open_url && source.filename);
  return (
    <button
      onClick={() => openable && onOpen(source.filename!)}
      disabled={!openable}
      className={`w-full flex items-start gap-2 rounded-lg border px-3 py-2 text-left ${
        openable
          ? 'bg-blue-50 border-blue-200 hover:bg-blue-100 cursor-pointer'
          : 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 cursor-default'
      }`}
      title={openable ? `Open ${title}` : 'This source has no in-app view'}
    >
      <FileText className={`w-4 h-4 mt-0.5 shrink-0 ${openable ? 'text-blue-600' : 'text-slate-400 dark:text-slate-500'}`} />
      <span className="min-w-0">
        <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Grounded in
        </span>
        <span className={`block text-sm font-medium truncate ${openable ? 'text-blue-800' : 'text-slate-700 dark:text-slate-300'}`}>
          {source.incident_id ? `${source.incident_id} — ` : ''}{title}
        </span>
      </span>
    </button>
  );
}

// ── source citations (open matched report in-app; dedup + clean labels) ───────
function Sources({ retrieval, onOpen }: { retrieval: SourceLink[]; onOpen: (filename: string) => void }) {
  if (!retrieval.length) return null;

  // Dedupe: retrieval can return several chunks of the same report. Key by
  // filename (or incident_id/title), keeping the highest-scoring instance.
  const seen = new Map<string, SourceLink>();
  for (const s of retrieval) {
    const key = s.filename || s.incident_id || s.title || JSON.stringify(s);
    const prev = seen.get(key);
    if (!prev || (s.score ?? 0) > (prev.score ?? 0)) seen.set(key, s);
  }
  const sources = Array.from(seen.values());

  return (
    <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
      <div className="flex items-center gap-1.5 mb-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
        <Database className="w-3.5 h-3.5" /> Sources
      </div>
      <div className="flex flex-wrap gap-1.5">
        {sources.map((s, i) => {
          // Prefer a human title; show incident id as a subtle prefix.
          const title = s.title || s.filename || 'report';
          const openable = !!(s.open_url && s.filename);
          const common = 'inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border max-w-[240px]';
          if (openable) {
            return (
              <button
                key={i}
                onClick={() => onOpen(s.filename!)}
                title={`Open ${title} in-app`}
                className={`${common} bg-blue-50 text-blue-700 border-blue-100 hover:bg-blue-100`}
              >
                <FileText className="w-3 h-3 shrink-0" />
                {s.incident_id && <span className="font-medium">{s.incident_id}</span>}
                <span className="truncate text-blue-600/80">{title}</span>
              </button>
            );
          }
          // Non-openable (e.g. a .md hit with no JSON view): show, don't fake a link.
          return (
            <span
              key={i}
              title="This source has no in-app view"
              className={`${common} bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700`}
            >
              {s.incident_id && <span className="font-medium">{s.incident_id}</span>}
              <span className="truncate">{title}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function FeedbackButtons({ value, onRate, onCorrect }: {
  value?: number | null;
  onRate: (v: 1 | -1) => void;
  onCorrect: (correction: string) => Promise<void>;
}) {
  // On thumbs-down, offer a correction box so the fix becomes learned knowledge.
  const [showCorrect, setShowCorrect] = useState(value === -1);
  const [text, setText] = useState('');
  const [saved, setSaved] = useState(false);

  const submit = async () => {
    const c = text.trim();
    if (!c) return;
    await onCorrect(c);
    setSaved(true);
    setText('');
    setTimeout(() => setShowCorrect(false), 1200);
  };

  return (
    <div className="pt-1">
      <div className="flex items-center gap-1">
        <span className="text-[11px] text-slate-400 dark:text-slate-500 mr-1">Was this helpful?</span>
        <button
          onClick={() => onRate(1)}
          title="Helpful"
          className={`p-1 rounded hover:bg-slate-100 dark:bg-slate-800 ${value === 1 ? 'text-green-600' : 'text-slate-400 dark:text-slate-500'}`}
        >
          <ThumbsUp className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => { onRate(-1); setShowCorrect(true); setSaved(false); }}
          title="Not helpful"
          className={`p-1 rounded hover:bg-slate-100 dark:bg-slate-800 ${value === -1 ? 'text-red-600' : 'text-slate-400 dark:text-slate-500'}`}
        >
          <ThumbsDown className="w-3.5 h-3.5" />
        </button>
      </div>

      {showCorrect && (
        <div className="mt-1.5">
          {saved ? (
            <div className="text-[11px] text-green-600">
              ✓ Thanks — I'll use this correction for similar questions.
            </div>
          ) : (
            <div className="flex items-start gap-1.5">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={2}
                placeholder="What's the correct answer? (this is saved and used for similar future questions)"
                className="flex-1 resize-none rounded-md border border-slate-300 dark:border-slate-600 px-2 py-1 text-xs outline-none focus:border-blue-500"
              />
              <button
                onClick={submit}
                disabled={!text.trim()}
                className="rounded-md bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-40"
              >
                Save
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Section header used throughout the incident response layout.
// A titled block of the answer. Headings used to lead with an emoji, which is
// the strongest visual tell of machine-written UI; they now carry their weight
// typographically instead.
function Section({ title, children }: {
  title: string; children: React.ReactNode;
}) {
  return (
    <section>
      <h4 className="mb-1.5 text-[13px] font-semibold text-slate-900 dark:text-slate-100">
        {title}
      </h4>
      {children}
    </section>
  );
}

// Human label + rendering hint per solution type.
const ACTION_LABEL: Record<string, string> = {
  SQL_QUERY: 'Data extraction (SQL)',
  CODE: 'Script / Terminal',
  CONFIG_CHANGE: 'Configuration change',
  INFRA_ACTION: 'Infrastructure action',
  INVESTIGATION_MEDIA: 'Screenshots / media',
  LOG_ANALYSIS: 'Log analysis',
  MANUAL_PROCEDURE: 'Manual procedure',
  DOC_REFERENCE: 'Documentation reference',
};

// One resolution step, formatted according to its solution type.
function StepBlock({ step }: { step: ResolutionStep }) {
  const type = step.action_type || 'MANUAL_PROCEDURE';
  const label = ACTION_LABEL[type] || 'Step';
  const art = step.artifact;

  // An irreversible step is outlined in amber so it cannot be skimmed past.
  const hazards = step.hazard ?? [];
  const isHazard = hazards.length > 0;

  return (
    <div
      className={
        isHazard
          ? 'rounded-lg border-2 border-amber-400 bg-amber-50 p-3'
          : 'rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-3'
      }
    >
      <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
        Step {step.step} — {step.title}
        <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {label}
        </span>
        {isHazard && (
          <span className="ml-2 rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-900">
            Irreversible
          </span>
        )}
      </div>
      {isHazard && (
        <div className="mt-1 text-xs text-amber-900">
          This step {hazards.join('; ')}.
          {step.hazard_ungrounded
            ? ' No incident report documents it — verify against a backup and a change ticket before running it.'
            : ' Confirm you are on the intended environment first.'}
        </div>
      )}
      {!isFiller(step.purpose) && (
        <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Purpose: {step.purpose}</div>
      )}
      {!isFiller(step.action) && (
        <div className="mt-1 text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{step.action}</div>
      )}

      {/* LOG_ANALYSIS renders its excerpt as a quote; code/config as a block. */}
      {art && type === 'LOG_ANALYSIS' && (
        <blockquote className="mt-2 border-l-4 border-slate-300 dark:border-slate-600 bg-white pl-3 py-1.5 text-xs font-mono text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
          {art.content}
        </blockquote>
      )}
      {art && type !== 'LOG_ANALYSIS' && (
        <div className="mt-2"><CodeBlock code={art.content} language={art.language} /></div>
      )}

      {!isFiller(step.validation) && (
        <div className="mt-1 text-xs text-slate-600 dark:text-slate-400 italic">Validate: {step.validation}</div>
      )}
      {step.evidence && step.evidence.length > 0 && (
        <div className="mt-1 text-xs text-blue-700">Evidence: {step.evidence.join(', ')}</div>
      )}
    </div>
  );
}

function AssistantCard({ answer, onOpen, feedback, onRate, onCorrect, messageId }: {
  answer: ChatAnswer; onOpen: (filename: string) => void;
  feedback?: number | null; onRate?: (v: 1 | -1) => void;
  onCorrect?: (correction: string) => Promise<void>;
  messageId?: string;
}) {
  const badge = confidenceBadge(answer.confidence);
  const linksInReasoning = extractLinks(answer.raw || '');
  // Steps render their own artifact; only show the rest in a trailing block.
  const stepArtifactContents = new Set(
    answer.steps.map((s) => (s as ResolutionStep).artifact?.content).filter(Boolean) as string[],
  );
  const unattachedArtifacts = answer.artifacts.filter((a) => !stepArtifactContents.has(a.content));
  // Warn on destructive SQL wherever it appears (step artifact or standalone).
  const hasDestructive =
    answer.artifacts.some((a) => a.language === 'sql' && isDestructiveSql(a.content)) ||
    answer.steps.some((s) => {
      const art = (s as ResolutionStep).artifact;
      return !!art && art.language === 'sql' && isDestructiveSql(art.content);
    });
  return (
    <div className="space-y-5 text-[15px] leading-relaxed text-slate-700 dark:text-slate-300">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 pb-3 dark:border-slate-800">
        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {answer.incident_type}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>
          {badge.label}
        </span>
        {answer.low_confidence && (
          <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
            <AlertTriangle className="w-3.5 h-3.5" /> low confidence — verify before acting
          </span>
        )}
      </div>

      {answer.security_note && (
        <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
          <ShieldAlert className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {answer.security_note}
        </div>
      )}

      {/* The report this answer is grounded in, up front. */}
      {answer.retrieval.length > 0 && (
        <SourceCard source={answer.retrieval[0]} onOpen={onOpen} />
      )}

      {/* Problem Summary */}
      {answer.answer && (
        <Section title="Problem Summary"><RichText text={answer.answer} /></Section>
      )}

      {/* Root Cause — omitted when the source documents none */}
      {!isFiller(answer.root_cause) && (
        <Section title="Root Cause">
          <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{answer.root_cause}</p>
        </Section>
      )}

      {/* Investigation — omitted when the source describes none */}
      {!isFiller(answer.investigation) && (
        <Section title="Investigation">
          <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{answer.investigation}</p>
        </Section>
      )}

      {/* Gate 4 — no documented resolution in the source report. */}
      {answer.no_documented_resolution && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900">
          No documented resolution was found in the retrieved incident report(s) for this issue.
        </div>
      )}

      {hasDestructive && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          Some suggested SQL is destructive (DROP/DELETE/TRUNCATE/UPDATE). Review carefully and back up before running.
        </div>
      )}

      {/* Resolution Steps — one labelled sub-block per solution type, in order */}
      {answer.steps.length > 0 && (
        <Section title="Resolution Steps">
          <div className="space-y-3">
            {answer.steps.map((s, i) => <StepBlock key={s.step ?? i} step={s as ResolutionStep} />)}
          </div>
          {answer.has_media && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <ImagePlus className="mt-0.5 w-3.5 h-3.5 shrink-0" />
              This report includes screenshots illustrating the above steps; open the
              original incident report to view them.
            </p>
          )}
        </Section>
      )}

      {/* AI suggestion — visibly separated from documented resolutions, because
          the distinction between "a report says this" and "the model proposes
          this" is the whole trust model of the tool. */}
      {answer.ai_suggestion && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 dark:border-violet-900/50 dark:bg-violet-950/30">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-violet-800 dark:text-violet-300">
            <Sparkles className="w-3.5 h-3.5" />
            AI-suggested — not a documented resolution
          </div>
          <p className="whitespace-pre-wrap text-sm text-violet-900 dark:text-violet-200">
            {answer.ai_suggestion}
          </p>
        </div>
      )}

      {/* Artifacts not already shown inside a step. */}
      {unattachedArtifacts.length > 0 && (
        <Section title={`Supporting ${unattachedArtifacts.length > 1 ? 'artifacts' : 'artifact'}`}>
          {unattachedArtifacts.map((a, i) => (
            <div key={i}>
              {a.title && <div className="text-xs text-slate-500 dark:text-slate-400 mb-0.5">{a.title}</div>}
              <CodeBlock code={a.content} language={a.language} />
            </div>
          ))}
        </Section>
      )}

      {/* Validation / Verification — omitted when nothing was documented */}
      {!isFiller(answer.validation) && (
        <Section title="Validation / Verification">
          <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{answer.validation}</p>
        </Section>
      )}

      {/* Additional Notes — omitted when it carries no real information */}
      {!isFiller(answer.additional_notes) && (
        <Section title="Additional Notes">
          <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{answer.additional_notes}</p>
        </Section>
      )}

      <Sources retrieval={answer.retrieval} onOpen={onOpen} />

      {linksInReasoning.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {linksInReasoning.map((url) => (
            <a key={url} href={url} target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">
              <ExternalLink className="w-3 h-3" /> {url.replace(/^https?:\/\//, '').slice(0, 40)}
            </a>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 pt-1">
        {onRate && onCorrect && (
          <FeedbackButtons value={feedback} onRate={onRate} onCorrect={onCorrect} />
        )}
        {messageId && (
          // Full HTML rendering of this answer, with the source report's
          // screenshots embedded — the chat card cannot show those inline.
          <a
            href={`/api/messages/${messageId}/html`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[11px] text-blue-600 hover:underline whitespace-nowrap"
            title="Open this answer with the report's screenshots"
          >
            <ExternalLink className="w-3 h-3" /> View with screenshots
          </a>
        )}
      </div>
    </div>
  );
}

export default function ChatbotModule() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(getActiveConversationId());
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [image, setImage] = useState<{ b64: string; name: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [openReport, setOpenReport] = useState<string | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Turn the current diagnosed conversation into a saved report, then open it.
  async function generateReportFromChat() {
    if (!activeId || reportBusy) return;
    setReportBusy(true);
    try {
      const res = await generateReport(activeId);
      setOpenReport(res.jsonFilename);          // open it in the in-app viewer
    } catch (err) {
      setMessages((m) => [...m, { role: 'error', text: (err as Error).message }]);
    } finally {
      setReportBusy(false);
    }
  }

  // Load the conversation list + restore the active thread on mount.
  useEffect(() => { refreshConversations(); }, []);
  useEffect(() => { if (activeId) restoreMessages(activeId); else setMessages([]); }, [activeId]);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  async function refreshConversations() {
    try { setConversations(await listConversations()); } catch { /* store may be empty */ }
  }

  async function restoreMessages(id: string) {
    try {
      const stored = await listMessages(id);
      setMessages(stored.map(fromStored).filter(Boolean) as Message[]);
    } catch {
      // Conversation vanished (deleted elsewhere) — reset to a clean slate.
      setActiveId(null); setActiveConversationId(null);
    }
  }

  function selectConversation(id: string | null) {
    setActiveId(id);
    setActiveConversationId(id);
  }

  async function removeConversation(id: string) {
    await deleteConversation(id);
    if (id === activeId) selectConversation(null);
    refreshConversations();
  }

  function onPickImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = String(reader.result).split(',')[1] ?? '';
      setImage({ b64, name: file.name });
    };
    reader.readAsDataURL(file);
  }

  // Rate an assistant answer; toggles off if the same thumb is clicked again.
  async function rate(index: number, messageId: string, current: number | null | undefined, value: 1 | -1) {
    const next = current === value ? null : value;
    setMessages((m) => {
      const msg = m[index];
      if (msg.role !== 'assistant') return m;
      return replaceAt(m, index, { ...msg, feedback: next });
    });
    try { await sendFeedback(messageId, next); } catch { /* non-critical */ }
  }

  const submit = async () => {
    const query = input.trim();
    if ((!query && !image) || loading) return; // supports text-only, image+text, image-only
    const links = extractLinks(query);
    setInput('');
    const sentImage = image;
    setImage(null);
    setMessages((m) => [...m, { role: 'user', text: query, hasImage: !!sentImage, links }]);
    setLoading(true);

    // A single placeholder bubble that grows with tokens, then is replaced by the
    // final card (or a chat bubble). Tracked by index for in-place updates.
    let streamIndex = -1;
    const putStreaming = (msg: Message) =>
      setMessages((m) => {
        if (streamIndex === -1) { streamIndex = m.length; return [...m, msg]; }
        return replaceAt(m, streamIndex, msg);
      });

    let acc = '';
    try {
      await streamChat(query, { imageB64: sentImage?.b64 ?? null, conversationId: activeId, links }, {
        onMeta: (cid) => {
          if (!activeId) { setActiveId(cid); setActiveConversationId(cid); }
        },
        // Greeting/smalltalk arrives whole; incident answers stream as tokens.
        onChat: (text) => putStreaming({ role: 'chat', text }),
        onToken: (t) => { acc += t; putStreaming({ role: 'streaming', text: acc }); },
        onError: (detail) => {
          // Loud failure instead of a fake answer.
          setMessages((m) => {
            const err: Message = { role: 'error', text: detail };
            return streamIndex === -1 ? [...m, err] : replaceAt(m, streamIndex, err);
          });
        },
        onDone: (answer, assistantMessageId) => {
          const finalMsg: Message = answer.is_chat
            ? { role: 'chat', text: answer.answer, clarify: answer.needs_clarification }
            : { role: 'assistant', answer, messageId: assistantMessageId, feedback: null };
          setMessages((m) => (streamIndex === -1 ? [...m, finalMsg] : replaceAt(m, streamIndex, finalMsg)));
          refreshConversations();
        },
      });
    } catch (err) {
      setMessages((m) => [...m, { role: 'error', text: (err as Error).message }]);
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  const hasMessages = messages.length > 0;

  return (
    // Full-bleed: App gives this module the bare <main>, so it owns the
    // viewport height and its own padding — that is what lets the transcript
    // scroll underneath a composer pinned to the bottom.
    <div className="flex h-screen">
      {/* ── History rail ─────────────────────────────────────────────────── */}
      <aside className="hidden md:flex w-64 shrink-0 flex-col border-r border-slate-200/80 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="p-3">
          <button
            onClick={() => selectConversation(null)}
            className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-750"
          >
            <Plus className="w-4 h-4" /> New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 ? (
            <p className="px-3 py-6 text-xs text-slate-400">No conversations yet.</p>
          ) : (
            <>
              <p className="px-3 pb-1 pt-2 text-[11px] font-medium text-slate-400">
                Recent
              </p>
              {conversations.map((c) => (
                <div
                  key={c.id}
                  onClick={() => selectConversation(c.id)}
                  className={`group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
                    c.id === activeId
                      ? 'bg-slate-200/70 text-slate-900 dark:bg-slate-800 dark:text-slate-100'
                      : 'text-slate-600 hover:bg-slate-200/50 dark:text-slate-400 dark:hover:bg-slate-800/60'
                  }`}
                >
                  <span className="flex-1 truncate">{c.title}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); removeConversation(c.id); }}
                    className="shrink-0 text-slate-400 opacity-0 transition hover:text-red-600 group-hover:opacity-100"
                    title="Delete conversation"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </>
          )}
        </div>
      </aside>

      {/* ── Transcript + composer ────────────────────────────────────────── */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {activeId && messages.some((m) => m.role === 'assistant') && (
          <div className="flex justify-end border-b border-slate-200/70 px-4 py-2 dark:border-slate-800">
            <button
              onClick={generateReportFromChat}
              disabled={reportBusy}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-800"
              title="Create an incident report from this conversation"
            >
              <FileText className="w-3.5 h-3.5" />
              {reportBusy ? 'Generating…' : 'Generate report'}
            </button>
          </div>
        )}

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {!hasMessages ? (
            // Empty state centred in the column, not floating at the top.
            <div className="flex h-full items-center justify-center px-4">
              <div className="w-full max-w-2xl text-center">
                <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
                  What incident are you looking at?
                </h1>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                  Describe the symptoms, paste an error, or attach a screenshot.
                </p>
                <div className="mt-6 grid gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => setInput(s)}
                      className="rounded-xl border border-slate-200 px-4 py-3 text-left text-sm text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto w-full max-w-3xl px-4 py-6">
              {messages.map((msg, i) => {
                // User turns: a compact bubble aligned right. The assistant's
                // reply is plain text on the page — no bubble, no avatar — so
                // long structured answers read as a document rather than as a
                // chat log squeezed into a box.
                if (msg.role === 'user') {
                  return (
                    <div key={i} className="mb-6 flex justify-end">
                      <div className="max-w-[80%] rounded-2xl bg-slate-100 px-4 py-2.5 text-slate-800 dark:bg-slate-800 dark:text-slate-100">
                        {msg.hasImage && (
                          <div className="mb-1 inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                            <ImagePlus className="w-3 h-3" /> screenshot attached
                          </div>
                        )}
                        <div className="whitespace-pre-wrap text-[15px] leading-relaxed">
                          {msg.text || <span className="italic text-slate-400">(image only)</span>}
                        </div>
                        {msg.links && msg.links.length > 0 && (
                          <div className="mt-1.5 space-y-0.5">
                            {msg.links.map((u) => (
                              <a key={u} href={u} target="_blank" rel="noopener noreferrer"
                                 className="flex items-center gap-1 text-xs text-slate-500 underline dark:text-slate-400">
                                <Link2 className="w-3 h-3" /> {u.replace(/^https?:\/\//, '').slice(0, 40)}
                              </a>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                }

                if (msg.role === 'error') {
                  return (
                    <div key={i} className="mb-6 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
                      <AlertTriangle className="mt-0.5 w-4 h-4 shrink-0" />
                      <span>{msg.text}</span>
                    </div>
                  );
                }

                if (msg.role === 'chat') {
                  // A clarification request keeps its amber treatment: the model
                  // deliberately declined to guess, which is not the same as a
                  // plain reply and should not look like one.
                  const clarify = msg.clarify;
                  return clarify ? (
                    <div key={i} className="mb-6 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                      <AlertTriangle className="mt-0.5 w-4 h-4 shrink-0" />
                      <span className="whitespace-pre-wrap">{msg.text}</span>
                    </div>
                  ) : (
                    <div key={i} className="mb-6 whitespace-pre-wrap text-[15px] leading-relaxed text-slate-700 dark:text-slate-200">
                      {msg.text}
                    </div>
                  );
                }

                if (msg.role === 'streaming') {
                  return (
                    <div key={i} className="mb-6 flex items-center gap-2 text-[15px] text-slate-400">
                      <Loader2 className="w-4 h-4 animate-spin" /> Analyzing…
                    </div>
                  );
                }

                const prevUser = [...messages.slice(0, i)].reverse().find((m) => m.role === 'user') as
                  | UserMessage | undefined;
                const question = prevUser?.text || msg.answer.answer || '';
                return (
                  <div key={i} className="mb-8">
                    <AssistantCard
                      answer={msg.answer}
                      onOpen={setOpenReport}
                      feedback={msg.feedback}
                      onRate={msg.messageId ? (v) => rate(i, msg.messageId!, msg.feedback, v) : undefined}
                      onCorrect={msg.messageId ? (c) => sendCorrection(question, c) : undefined}
                      messageId={msg.messageId}
                    />
                  </div>
                );
              })}

              {loading && !messages.some((m) => m.role === 'streaming') && (
                <div className="mb-6 flex items-center gap-2 text-[15px] text-slate-400">
                  <Loader2 className="w-4 h-4 animate-spin" /> Thinking…
                </div>
              )}
            </div>
          )}
        </div>

        {/* Composer: pinned, on a fading backdrop so text scrolls out under it. */}
        <div className="shrink-0 bg-gradient-to-t from-white via-white to-transparent px-4 pb-4 pt-2 dark:from-slate-950 dark:via-slate-950">
          <div className="mx-auto w-full max-w-3xl">
            {image && (
              <div className="mb-2 inline-flex items-center gap-2 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                <ImagePlus className="w-3.5 h-3.5" /> {image.name}
                <button onClick={() => setImage(null)} className="text-slate-400 hover:text-red-500">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <div className="flex items-end gap-2 rounded-3xl border border-slate-200 bg-white px-3 py-2 shadow-sm transition focus-within:border-slate-300 focus-within:shadow-md dark:border-slate-700 dark:bg-slate-800">
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPickImage} />
              <button
                onClick={() => fileRef.current?.click()}
                className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700"
                title="Attach a screenshot"
              >
                <ImagePlus className="w-5 h-5" />
              </button>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                placeholder="Ask about an incident…"
                className="max-h-48 flex-1 resize-none bg-transparent py-2 text-[15px] text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100"
              />
              <button
                onClick={submit}
                disabled={loading || (!input.trim() && !image)}
                className="rounded-full bg-slate-900 p-2 text-white transition hover:bg-slate-700 disabled:opacity-30 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
                aria-label="Send"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>

            <p className="mt-2 text-center text-[11px] text-slate-400">
              Answers are grounded in your incident reports — verify before acting.
            </p>
          </div>
        </div>
      </div>

      {/* In-app report viewer for a cited source */}
      {openReport && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-6 backdrop-blur-sm" onClick={() => setOpenReport(null)}>
          <div className="w-full max-w-4xl rounded-xl bg-slate-50 shadow-2xl dark:bg-slate-900" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-end p-2">
              <button onClick={() => setOpenReport(null)} className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-200 hover:text-slate-900 dark:hover:bg-slate-800">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="px-4 pb-6">
              <ReportViewer filename={openReport} onBack={() => setOpenReport(null)} onEdit={() => setOpenReport(null)} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
