"use client";
import React, { useEffect, useState, type ReactNode } from "react";
import { 
  Check, 
  CheckCircle2, 
  CircleAlert, 
  Clock3, 
  Copy, 
  FileCheck2, 
  Moon, 
  ShieldCheck, 
  Sun, 
  SunMoon 
} from "lucide-react";

export function Page({
  title,
  subtitle,
  actions,
  children,
  eyebrow = "Insurance workspace"
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="page-shell">
      <div className="page-head">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h1 className="page-title">{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="actions">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

export function Card({
  children,
  className = "",
  style
}: {
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <section className={"card " + className} style={style}>
      {children}
    </section>
  );
}

export function Metric({
  label,
  value,
  note,
  icon,
  trend = "normal"
}: {
  label: string;
  value: ReactNode;
  note?: string;
  icon?: ReactNode;
  trend?: "normal" | "warning" | "danger" | "success";
}) {
  return (
    <Card className="metric">
      <div className="metric-label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {icon}
        <span>{label}</span>
      </div>
      <div className="metric-value">{value}</div>
      {note && (
        <div className={`metric-trend ${trend !== "normal" ? trend : ""}`}>
          {note}
        </div>
      )}
    </Card>
  );
}

export function Badge({
  children,
  tone = "neutral"
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  return <span className={"badge " + tone}>{children}</span>;
}

export function Empty({
  text,
  icon,
  action
}: {
  text: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      {icon && <div style={{ color: "var(--muted)", opacity: 0.8 }}>{icon}</div>}
      <div>{text}</div>
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}

export function Button({
  children,
  className = "",
  ...props
}: {
  children: ReactNode;
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={"btn " + className} {...props}>
      {children}
    </button>
  );
}

export function DataBadge({ status }: { status: string }) {
  const s = (status || "unknown").toLowerCase();
  const tone =
    s.includes("approved") ||
    s.includes("verified") ||
    s.includes("resolved") ||
    s.includes("complete") ||
    s.includes("active")
      ? "success"
      : s.includes("reject") || s.includes("fail") || s.includes("breach") || s.includes("inactive")
      ? "danger"
      : s.includes("pending") ||
        s.includes("review") ||
        s.includes("open") ||
        s.includes("missing") ||
        s.includes("escalat")
      ? "warning"
      : "info";

  return <Badge tone={tone}>{(status || "unknown").replaceAll("_", " ")}</Badge>;
}

export function StatusIcon({ status }: { status: string }) {
  const s = (status || "").toLowerCase();
  if (["approved", "verified", "complete", "resolved", "active"].includes(s)) {
    return <CheckCircle2 size={15} color="var(--success)" />;
  }
  if (["pending", "under_review", "review", "pending_evidence", "escalated"].includes(s)) {
    return <Clock3 size={15} color="var(--warning)" />;
  }
  if (["rejected", "failed", "error", "inactive", "breached"].includes(s)) {
    return <CircleAlert size={15} color="var(--danger)" />;
  }
  if (s.includes("policy")) {
    return <ShieldCheck size={15} color="var(--blue)" />;
  }
  return <FileCheck2 size={15} color="var(--muted)" />;
}

/* ==========================================================================
   Dual-Mode Theme Toggle (Light / Dark / System)
   ========================================================================== */

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");

  useEffect(() => {
    const saved = (localStorage.getItem("flowa-theme") as "light" | "dark" | "system") || "system";
    setTheme(saved);
    applyTheme(saved);
  }, []);

  function applyTheme(t: "light" | "dark" | "system") {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    if (t === "system") {
      root.removeAttribute("data-theme");
      const prefersDark =
        typeof window !== "undefined" && typeof window.matchMedia === "function"
          ? window.matchMedia("(prefers-color-scheme: dark)").matches
          : false;
      if (prefersDark) {
        root.classList.add("dark");
      } else {
        root.classList.remove("dark");
      }
    } else {
      root.setAttribute("data-theme", t);
      if (t === "dark") {
        root.classList.add("dark");
      } else {
        root.classList.remove("dark");
      }
    }
  }

  function cycle() {
    const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
    setTheme(next);
    localStorage.setItem("flowa-theme", next);
    applyTheme(next);
  }

  return (
    <button 
      className="icon-btn" 
      onClick={cycle} 
      title={`Theme: ${theme.toUpperCase()} (Click to cycle)`} 
      aria-label="Toggle color theme"
    >
      {theme === "light" ? (
        <Sun size={17} />
      ) : theme === "dark" ? (
        <Moon size={17} />
      ) : (
        <SunMoon size={17} />
      )}
    </button>
  );
}

/* ==========================================================================
   Code Block with One-Click Copy & Inline Syntax Preview
   ========================================================================== */

export function CodeBlock({ code, language = "text" }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <div style={{ margin: "12px 0" }}>
      <div className="code-block-header">
        <span>{language.toUpperCase()}</span>
        <button 
          onClick={copy} 
          style={{ display: "flex", alignItems: "center", gap: 5, color: copied ? "var(--success)" : "inherit" }}
          aria-label="Copy code block"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          <span>{copied ? "Copied!" : "Copy"}</span>
        </button>
      </div>
      <pre style={{ margin: 0, borderRadius: "0 0 8px 8px" }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

/* ==========================================================================
   Bespoke Markdown Parser (Headers, lists, bold, inline code, fenced code)
   Zero external dependencies for rapid, accessible AI response streaming
   ========================================================================== */

export function MarkdownRenderer({ content }: { content: string }) {
  if (!content) return null;

  // Split content by code blocks first
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="markdown-body">
      {parts.map((part, index) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const lines = part.slice(3, -3).trim().split("\n");
          let language = "text";
          let code = part.slice(3, -3).trim();
          if (lines.length > 0 && lines[0].trim() && !lines[0].includes(" ")) {
            language = lines[0].trim();
            code = lines.slice(1).join("\n");
          }
          return <CodeBlock key={index} code={code} language={language} />;
        }

        // Render regular markdown text
        return <FormattedParagraphs key={index} text={part} />;
      })}
    </div>
  );
}

function FormattedParagraphs({ text }: { text: string }) {
  const lines = text.split("\n");
  const elements: ReactNode[] = [];
  let currentList: { type: "ul" | "ol"; items: string[] } | null = null;
  let currentParagraph: string[] = [];

  function flushParagraph() {
    if (currentParagraph.length > 0) {
      elements.push(
        <p key={`p-${elements.length}`} style={{ margin: "0 0 12px" }}>
          {currentParagraph.map((line, li) => (
            <React.Fragment key={li}>
              {renderInline(line)}
              {li < currentParagraph.length - 1 && <br />}
            </React.Fragment>
          ))}
        </p>
      );
      currentParagraph = [];
    }
  }

  function flushList() {
    if (currentList) {
      if (currentList.type === "ul") {
        elements.push(
          <ul key={`ul-${elements.length}`} style={{ margin: "0 0 12px", paddingLeft: 20 }}>
            {currentList.items.map((item, ii) => (
              <li key={ii} style={{ marginBottom: 4 }}>
                {renderInline(item)}
              </li>
            ))}
          </ul>
        );
      } else {
        elements.push(
          <ol key={`ol-${elements.length}`} style={{ margin: "0 0 12px", paddingLeft: 20 }}>
            {currentList.items.map((item, ii) => (
              <li key={ii} style={{ marginBottom: 4 }}>
                {renderInline(item)}
              </li>
            ))}
          </ol>
        );
      }
      currentList = null;
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (trimmed.startsWith("### ")) {
      flushParagraph();
      flushList();
      elements.push(
        <h3 key={`h3-${elements.length}`} style={{ fontSize: 16, fontWeight: 700, margin: "16px 0 8px" }}>
          {renderInline(trimmed.slice(4))}
        </h3>
      );
      continue;
    }

    if (trimmed.startsWith("## ")) {
      flushParagraph();
      flushList();
      elements.push(
        <h2 key={`h2-${elements.length}`} style={{ fontSize: 18, fontWeight: 700, margin: "18px 0 10px" }}>
          {renderInline(trimmed.slice(3))}
        </h2>
      );
      continue;
    }

    if (trimmed.startsWith("# ")) {
      flushParagraph();
      flushList();
      elements.push(
        <h1 key={`h1-${elements.length}`} style={{ fontSize: 20, fontWeight: 700, margin: "20px 0 12px" }}>
          {renderInline(trimmed.slice(2))}
        </h1>
      );
      continue;
    }

    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      flushParagraph();
      if (!currentList || currentList.type !== "ul") {
        flushList();
        currentList = { type: "ul", items: [] };
      }
      currentList.items.push(trimmed.slice(2));
      continue;
    }

    const numMatch = trimmed.match(/^\d+\.\s(.*)$/);
    if (numMatch) {
      flushParagraph();
      if (!currentList || currentList.type !== "ol") {
        flushList();
        currentList = { type: "ol", items: [] };
      }
      currentList.items.push(numMatch[1]);
      continue;
    }

    flushList();
    currentParagraph.push(line);
  }

  flushParagraph();
  flushList();

  return <>{elements}</>;
}

function renderInline(text: string): ReactNode {
  const regex = /(\*\*.*?\*\*|`.*?`)/g;
  const tokens = text.split(regex);

  return tokens.map((tok, i) => {
    if (tok.startsWith("**") && tok.endsWith("**")) {
      return <strong key={i}>{tok.slice(2, -2)}</strong>;
    }
    if (tok.startsWith("`") && tok.endsWith("`")) {
      return <code key={i}>{tok.slice(1, -1)}</code>;
    }
    return <React.Fragment key={i}>{tok}</React.Fragment>;
  });
}
