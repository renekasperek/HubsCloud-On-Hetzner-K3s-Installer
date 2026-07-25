import { Link } from "react-router-dom";

const HF_HOME = "https://hubsfoundation.org/";
const HF_HCE_DOCS = "https://docs.hubsfoundation.org/";
const HF_GITHUB = "https://github.com/Hubs-Foundation";

export const INSTALLER_DOCS_PATH = "/docs";

export type ResourceLink =
  | { kind: "internal"; to: string; label: string }
  | { kind: "external"; href: string; label: string };

/** Installer docs first; general Hubs Foundation resources are separate. */
export const RESOURCE_LINKS: ResourceLink[] = [
  { kind: "internal", to: INSTALLER_DOCS_PATH, label: "Installer docs" },
  { kind: "external", href: HF_HOME, label: "Hubs Foundation" },
  { kind: "external", href: HF_HCE_DOCS, label: "Hubs CE docs" },
  { kind: "external", href: HF_GITHUB, label: "GitHub" },
];

type HubsFoundationLogoProps = {
  height?: number;
  className?: string;
};

export function HubsFoundationLogo({ height = 32, className = "" }: HubsFoundationLogoProps) {
  return (
    <img
      src="/hubs-foundation-logo.png"
      alt="Hubs Foundation"
      className={`hf-logo${className ? ` ${className}` : ""}`}
      height={height}
      width={Math.round(height * (595 / 556))}
      decoding="async"
    />
  );
}

export function HubsFoundationBrand({ compact = false }: { compact?: boolean }) {
  return (
    <a
      href={HF_HOME}
      className="hf-brand"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Hubs Foundation (opens in new tab)"
    >
      <HubsFoundationLogo height={compact ? 28 : 36} />
      {!compact && <span className="hf-brand-name">Hubs Foundation</span>}
    </a>
  );
}

export function ResourceLinkRow({ className = "" }: { className?: string }) {
  return (
    <nav className={`hf-links${className ? ` ${className}` : ""}`} aria-label="Resources">
      {RESOURCE_LINKS.map((item) =>
        item.kind === "internal" ? (
          <Link key={item.to} to={item.to}>
            {item.label}
          </Link>
        ) : (
          <a key={item.href} href={item.href} target="_blank" rel="noopener noreferrer">
            {item.label}
          </a>
        )
      )}
    </nav>
  );
}

/** @deprecated use ResourceLinkRow */
export const HubsFoundationLinkRow = ResourceLinkRow;

export function HubsFoundationAttribution() {
  return (
    <div className="hf-attribution">
      <HubsFoundationBrand />
      <p className="hf-attribution-text">
        Deploy{" "}
        <a href={HF_HCE_DOCS} target="_blank" rel="noopener noreferrer">
          Hubs Community Edition
        </a>{" "}
        on your own infrastructure. Read the{" "}
        <Link to={INSTALLER_DOCS_PATH}>installer documentation</Link> for this tool; Hubs is open source and
        maintained by the{" "}
        <a href={HF_HOME} target="_blank" rel="noopener noreferrer">
          Hubs Foundation
        </a>
        .
      </p>
      <ResourceLinkRow />
    </div>
  );
}
