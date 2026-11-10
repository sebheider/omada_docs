import { useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({ gfm: true, breaks: true });

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

/** Render user-supplied markdown. The HTML output is always sanitised with DOMPurify. */
export function Markdown({ text, className }: { text: string | null | undefined; className?: string }) {
  const html = useMemo(() => {
    if (!text) return '';
    const raw = marked.parse(text, { async: false });
    return DOMPurify.sanitize(raw, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ['style', 'iframe', 'form', 'input', 'script', 'object', 'embed'],
      FORBID_ATTR: ['style'],
    });
  }, [text]);
  if (!text) return null;
  return (
    <div
      className={`prose prose-sm max-w-none dark:prose-invert prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-100 prose-pre:text-slate-800 dark:prose-pre:bg-slate-800 dark:prose-pre:text-slate-100 ${className ?? ''}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
