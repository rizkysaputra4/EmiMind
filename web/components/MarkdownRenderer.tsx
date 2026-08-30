"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { CitationChip } from "./CitationChip";
import { ShieldCheck, AlertCircle, Info } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
  onSelectCitation?: (tag: string) => void;
}

// Robust regex matching citation tags like [TICKER-DOCTYPE-PERIOD#pPAGE]
const CITATION_REGEX = /(\[[A-Z0-9_]{2,10}-[A-Z0-9_]+-[A-Z0-9_]+(?:#p\d+)?\])/gi;

export function MarkdownRenderer({ content, onSelectCitation }: MarkdownRendererProps) {
  // Helper to replace raw citation strings with CitationChip components in text nodes
  const processChildren = (children: React.ReactNode): React.ReactNode => {
    if (typeof children === "string") {
      const parts = children.split(CITATION_REGEX);
      if (parts.length === 1) return children;

      return parts.map((part, index) => {
        if (CITATION_REGEX.test(part)) {
          return (
            <CitationChip
              key={index}
              tag={part}
              onClick={(tag) => onSelectCitation?.(tag)}
            />
          );
        }
        return part;
      });
    }

    if (Array.isArray(children)) {
      return React.Children.map(children, (child) => processChildren(child));
    }

    if (React.isValidElement(children) && children.props?.children) {
      return React.cloneElement(children as React.ReactElement<any>, {
        children: processChildren(children.props.children),
      });
    }

    return children;
  };

  return (
    <div className="prose prose-invert max-w-none text-xs sm:text-sm leading-relaxed text-slate-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          // Headers
          h1: ({ children, ...props }) => (
            <h1
              className="text-base sm:text-lg font-bold text-slate-100 mt-4 mb-2 pb-1.5 border-b border-slate-800 flex items-center gap-2"
              {...props}
            >
              {processChildren(children)}
            </h1>
          ),
          h2: ({ children, ...props }) => {
            const textContent = String(children);
            const isMissingDataSection =
              textContent.toLowerCase().includes("not disclosed") ||
              textContent.toLowerCase().includes("missing data");

            return (
              <h2
                className={`text-xs sm:text-sm font-bold mt-4 mb-2 flex items-center gap-1.5 ${
                  isMissingDataSection ? "text-amber-400" : "text-blue-300"
                }`}
                {...props}
              >
                {isMissingDataSection && <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                {processChildren(children)}
              </h2>
            );
          },
          h3: ({ children, ...props }) => (
            <h3
              className="text-xs font-semibold text-indigo-300 mt-3 mb-1.5"
              {...props}
            >
              {processChildren(children)}
            </h3>
          ),
          h4: ({ children, ...props }) => (
            <h4 className="text-xs font-medium text-slate-300 mt-2 mb-1" {...props}>
              {processChildren(children)}
            </h4>
          ),

          // Paragraphs & Disclaimers
          p: ({ children, ...props }) => {
            const rawString = typeof children === "string" ? children : "";
            const isDisclaimer =
              rawString.toLowerCase().includes("disclaimer: emimind") ||
              rawString.toLowerCase().startsWith("disclaimer:");

            if (isDisclaimer) {
              return (
                <div className="mt-4 rounded-lg border border-slate-800/80 bg-slate-950/80 px-3.5 py-2.5 text-[11px] text-slate-400 flex items-start gap-2 shadow-inner">
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
                  <div className="leading-relaxed italic text-slate-400">
                    {processChildren(children)}
                  </div>
                </div>
              );
            }

            return (
              <p className="my-2 leading-relaxed text-slate-200" {...props}>
                {processChildren(children)}
              </p>
            );
          },

          // Lists
          ul: ({ children, ...props }) => (
            <ul className="my-2 space-y-1 pl-4 list-disc marker:text-blue-500" {...props}>
              {children}
            </ul>
          ),
          ol: ({ children, ...props }) => (
            <ol className="my-2 space-y-1 pl-4 list-decimal marker:text-blue-400" {...props}>
              {children}
            </ol>
          ),
          li: ({ children, ...props }) => (
            <li className="text-xs leading-relaxed text-slate-200" {...props}>
              {processChildren(children)}
            </li>
          ),

          // Bold & Italic & Blockquotes
          strong: ({ children, ...props }) => (
            <strong className="font-semibold text-slate-100" {...props}>
              {processChildren(children)}
            </strong>
          ),
          em: ({ children, ...props }) => {
            const textContent = String(children);
            if (textContent.toLowerCase().startsWith("disclaimer:")) {
              return (
                <span className="block mt-3 rounded-lg border border-slate-800/80 bg-slate-900/60 p-2.5 text-[11px] text-slate-400 italic">
                  {textContent}
                </span>
              );
            }
            return (
              <em className="italic text-slate-300" {...props}>
                {processChildren(children)}
              </em>
            );
          },
          blockquote: ({ children, ...props }) => (
            <blockquote
              className="my-3 border-l-2 border-blue-500 bg-blue-950/20 px-3.5 py-2 rounded-r-md text-xs italic text-slate-300 leading-relaxed"
              {...props}
            >
              {processChildren(children)}
            </blockquote>
          ),

          // Tables
          table: ({ children, ...props }) => (
            <div className="my-3 w-full overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/80 shadow-md">
              <table className="w-full text-left border-collapse text-xs" {...props}>
                {children}
              </table>
            </div>
          ),
          thead: ({ children, ...props }) => (
            <thead
              className="bg-slate-900/90 border-b border-slate-800 text-slate-300 font-mono uppercase text-[10px] sm:text-[11px] font-semibold tracking-wider"
              {...props}
            >
              {children}
            </thead>
          ),
          tbody: ({ children, ...props }) => (
            <tbody className="divide-y divide-slate-800/60" {...props}>
              {children}
            </tbody>
          ),
          tr: ({ children, ...props }) => (
            <tr
              className="hover:bg-slate-900/40 transition-colors even:bg-slate-900/20"
              {...props}
            >
              {children}
            </tr>
          ),
          th: ({ children, ...props }) => (
            <th
              className="px-3.5 py-2 font-semibold text-slate-300 border-r border-slate-800/60 last:border-r-0"
              {...props}
            >
              {processChildren(children)}
            </th>
          ),
          td: ({ children, ...props }) => (
            <td
              className="px-3.5 py-2 text-slate-200 border-r border-slate-800/40 last:border-r-0 leading-relaxed"
              {...props}
            >
              {processChildren(children)}
            </td>
          ),

          // Code & Citations
          code: ({ children, ...props }) => {
            const rawContent = String(children).trim();
            // If the code snippet is a citation tag like `[LSIP-PROFILE-2026Q2#p1]`
            if (CITATION_REGEX.test(rawContent)) {
              return (
                <CitationChip
                  tag={rawContent}
                  onClick={(tag) => onSelectCitation?.(tag)}
                />
              );
            }
            return (
              <code
                className="font-mono text-xs bg-slate-900 text-blue-300 px-1.5 py-0.5 rounded border border-slate-800"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children, ...props }) => (
            <pre
              className="p-3 my-2 rounded-lg bg-slate-950 border border-slate-800 overflow-x-auto font-mono text-xs text-slate-300"
              {...props}
            >
              {children}
            </pre>
          ),
          hr: ({ ...props }) => (
            <hr className="my-3 border-slate-800" {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
