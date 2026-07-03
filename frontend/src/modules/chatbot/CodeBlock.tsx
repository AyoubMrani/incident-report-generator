import React, { useEffect, useRef, useState } from 'react';
import { Copy, Check } from 'lucide-react';
import Prism from 'prismjs';
import 'prismjs/themes/prism-tomorrow.css';
// Languages the incident bot actually emits. Order matters: some depend on markup.
import 'prismjs/components/prism-sql';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-json';

const ALIASES: Record<string, string> = {
  '': 'sql', // supporting_sql blocks have no fence language — default to SQL
  sh: 'bash', shell: 'bash', console: 'bash',
  py: 'python', js: 'javascript', ts: 'typescript',
};

function resolveLang(lang?: string): string {
  const l = (lang || '').toLowerCase();
  const resolved = ALIASES[l] ?? l;
  return Prism.languages[resolved] ? resolved : 'sql';
}

export function CodeBlock({ code, language }: { code: string; language?: string }) {
  const ref = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);
  const lang = resolveLang(language);

  useEffect(() => {
    if (ref.current) Prism.highlightElement(ref.current);
  }, [code, lang]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked — ignore */ }
  };

  return (
    <div className="group relative my-2 overflow-hidden rounded-lg border border-gray-700 bg-[#2d2d2d]">
      <div className="flex items-center justify-between px-3 py-1 bg-black/30 text-[10px] uppercase tracking-wide text-gray-400">
        <span>{lang}</span>
        <button
          onClick={copy}
          className="inline-flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity hover:text-white"
          title="Copy code"
        >
          {copied ? <><Check className="w-3 h-3" /> copied</> : <><Copy className="w-3 h-3" /> copy</>}
        </button>
      </div>
      <pre className="!m-0 overflow-x-auto p-3 text-xs leading-relaxed">
        <code ref={ref} className={`language-${lang}`}>{code}</code>
      </pre>
    </div>
  );
}

// Split assistant free-text into plain segments and fenced ```code``` blocks so
// each can render appropriately (prose vs highlighted CodeBlock).
export interface Segment { type: 'text' | 'code'; content: string; lang?: string }

export function splitFencedCode(text: string): Segment[] {
  const segments: Segment[] = [];
  const fence = /```(\w+)?\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = fence.exec(text)) !== null) {
    if (m.index > last) segments.push({ type: 'text', content: text.slice(last, m.index) });
    segments.push({ type: 'code', content: m[2].replace(/\n$/, ''), lang: m[1] });
    last = fence.lastIndex;
  }
  if (last < text.length) segments.push({ type: 'text', content: text.slice(last) });
  return segments;
}
