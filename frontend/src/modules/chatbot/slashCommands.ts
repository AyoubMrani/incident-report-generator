// Slash commands: composer shortcuts that expand to a query template.
//
// Deliberately templates the user fills in, not canned one-click questions —
// unlike the follow-up suggestion chips (which ask a complete, specific
// question immediately), a command like /rca needs the *incident* filled in
// before it means anything. The placeholder text between the double
// brackets marks what to replace and is selected automatically so typing
// immediately overwrites it, the same convention snippet expanders use.
//
// This is pure client-side templating — no backend involved, no new prompt
// path. It steers what the user types into the query the existing pipeline
// already handles best (a concrete question referencing systems/errors/ids),
// rather than adding a new answer mode.

export interface SlashCommand {
  /** Typed after "/", case-insensitive. */
  command: string;
  label: string;
  description: string;
  /** Inserted into the composer. `[[...]]` marks the segment to select. */
  template: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    command: 'rca',
    label: '/rca',
    description: 'Root cause analysis for an incident',
    template: 'What is the root cause of [[describe the symptom or error]]?',
  },
  {
    command: 'sql',
    label: '/sql',
    description: 'Ask for the exact query used to fix something',
    template: 'What is the exact SQL used to [[describe the fix]]?',
  },
  {
    command: 'steps',
    label: '/steps',
    description: 'Ask for the full resolution procedure',
    template: 'What are the full resolution steps for [[describe the incident]]?',
  },
  {
    command: 'summarize',
    label: '/summarize',
    description: 'Summarize this conversation so far',
    template: 'Summarize this conversation and the resolution so far.',
  },
  {
    command: 'validate',
    label: '/validate',
    description: 'Ask how to confirm a fix actually worked',
    template: 'How do I validate that [[the fix]] actually resolved the issue?',
  },
  {
    command: 'similar',
    label: '/similar',
    description: 'Find incidents similar to this one',
    template: 'What other incidents are similar to [[describe this one]]?',
  },
];

/** Commands whose name starts with the typed fragment (after the "/"). */
export function matchSlashCommands(fragment: string): SlashCommand[] {
  const f = fragment.toLowerCase();
  return SLASH_COMMANDS.filter((c) => c.command.startsWith(f));
}

/**
 * Does `value` look like the user is mid-typing a slash command right now?
 * True only when "/" starts the composer — a "/" appearing mid-sentence
 * (a file path, a fraction) must not trigger the picker.
 */
export function activeSlashFragment(value: string): string | null {
  const m = value.match(/^\/([a-zA-Z]*)$/);
  return m ? m[1] : null;
}

/** Selection range of the `[[...]]` placeholder in an expanded template, if any. */
export function placeholderRange(text: string): { start: number; end: number } | null {
  const start = text.indexOf('[[');
  if (start === -1) return null;
  const end = text.indexOf(']]', start);
  if (end === -1) return null;
  return { start, end: end + 2 };
}

/** Strip the `[[` `]]` markers, leaving the plain placeholder text visible. */
export function stripPlaceholderMarkers(text: string): string {
  return text.replace(/\[\[|\]\]/g, '');
}
