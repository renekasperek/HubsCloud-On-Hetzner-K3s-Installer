import { Link } from "react-router-dom";

const HF_HOME = "https://hubsfoundation.org/";
const HF_HCE_DOCS = "https://docs.hubsfoundation.org/";
const HF_GITHUB = "https://github.com/Hubs-Foundation";
const INSTALLER_GITHUB = "https://github.com/splexit/HubsCloud-On-Hetzner-K3s-Installer";

export { HF_HOME, INSTALLER_GITHUB };

export const INSTALLER_DOCS_PATH = "/docs";

export type ResourceLink =
  | { kind: "internal"; to: string; label: string }
  | { kind: "external"; href: string; label: string };

/** Installer docs first; general Hubs Foundation resources are separate. */
export const RESOURCE_LINKS: ResourceLink[] = [
  { kind: "internal", to: INSTALLER_DOCS_PATH, label: "Installer docs" },
  { kind: "external", href: INSTALLER_GITHUB, label: "GitHub repo" },
  { kind: "external", href: HF_HOME, label: "Hubs Foundation" },
  { kind: "external", href: HF_HCE_DOCS, label: "Hubs CE docs" },
  { kind: "external", href: HF_GITHUB, label: "Hubs GitHub" },
];

const HUBS_HORIZ_LOGO = "/images/hubs_onwhite_lalpha_horiz_main.png";
const HUBS_VERT_LOGO = "/images/hubs_black_vert_main.png";
const HETZNER_LOGO = "/images/Logo_Hetzner.svg.webp";

type BrandLogoProps = {
  height?: number;
  className?: string;
};

export function InstallerTopBrand({ height = 28, className = "" }: BrandLogoProps) {
  return (
    <img
      src={HUBS_HORIZ_LOGO}
      alt="Hubs"
      className={`brand-logo brand-logo-horiz${className ? ` ${className}` : ""}`}
      style={{ height }}
      decoding="async"
    />
  );
}

export function InfrastructureBrandMark() {
  return (
    <div className="infra-brand-mark" aria-label="Hubs on Hetzner Infrastructure">
      <img
        src={HUBS_VERT_LOGO}
        alt="Hubs"
        className="brand-logo brand-logo-vert"
        decoding="async"
      />
      <span className="infra-brand-on" aria-hidden>
        on
      </span>
      <img
        src={HETZNER_LOGO}
        alt="Hetzner"
        className="brand-logo brand-logo-hetzner"
        decoding="async"
      />
    </div>
  );
}

export function LandingHeroBrand() {
  return (
    <header className="landing-hero">
      <InfrastructureBrandMark />
      <p className="landing-hero-tagline">Hetzner Infrastructure</p>
      <p className="landing-hero-lead">
        Guided setup for Hubs Community Edition on Hetzner Cloud. Live provisioning status and
        secrets handoff — runs locally on your machine.
      </p>
    </header>
  );
}

/** @deprecated use InstallerTopBrand or InfrastructureBrandMark */
export function HubsFoundationLogo({ height = 32, className = "" }: BrandLogoProps) {
  return <InstallerTopBrand height={height} className={className} />;
}

/** @deprecated use InstallerTopBrand */
export function HubsFoundationBrand({ compact = false }: { compact?: boolean }) {
  return <InstallerTopBrand height={compact ? 28 : 36} />;
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

/** @deprecated use LandingHeroBrand */
export function HubsFoundationAttribution() {
  return <LandingHeroBrand />;
}
