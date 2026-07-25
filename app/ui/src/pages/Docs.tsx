import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { marked } from "marked";
import { api } from "../api";

marked.setOptions({
  gfm: true,
  breaks: false,
});

type InstallerDocs = {
  title: string;
  markdown: string;
  source: string;
};

export function DocsPage() {
  const [docs, setDocs] = useState<InstallerDocs | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<InstallerDocs>("/docs/installer")
      .then(setDocs)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load documentation"));
  }, []);

  const html = docs ? marked.parse(docs.markdown) : "";

  return (
    <div className="docs-page">
      <div className="docs-header">
        <Link to="/" className="btn btn-ghost" style={{ paddingLeft: 0 }}>
          ← Back
        </Link>
        <h1>{docs?.title || "Installer documentation"}</h1>
        <p className="muted" style={{ margin: 0 }}>
          This page shows the installer README — prerequisites, recovery, security, and operations for this tool.
        </p>
      </div>

      {error && (
        <div className="panel bad-text" style={{ marginBottom: 20 }}>
          {error}
        </div>
      )}

      {!docs && !error && <p className="muted">Loading…</p>}

      {docs && (
        <article
          className="docs-content panel"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}
    </div>
  );
}
