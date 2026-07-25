import { Link } from "react-router-dom";
import { ClusterTopology } from "../components/ClusterTopology";
import { HubsFoundationAttribution, HubsFoundationBrand, ResourceLinkRow, INSTALLER_DOCS_PATH } from "../components/HubsFoundationLinks";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-start">
          <HubsFoundationBrand compact />
          <span className="topbar-divider" aria-hidden />
          <Link to="/" className="topbar-product">
            Hubs Installer
          </Link>
        </div>
        <div className="topbar-end">
          <ResourceLinkRow className="topbar-hf-links" />
          <span className="topbar-meta">127.0.0.1 · v1</span>
        </div>
      </header>
      <main className="main">{children}</main>
      <footer className="app-footer">
        <HubsFoundationBrand compact />
        <ResourceLinkRow />
        <span className="muted app-footer-meta">Local provisioning tool · not affiliated with hosting</span>
      </footer>
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="landing-wrap">
      <div className="landing-cluster">
        <HubsFoundationAttribution />
        <h1>Hubs Installer</h1>
        <p style={{ fontSize: 20, margin: "0 0 8px", fontWeight: 500, color: "var(--text)" }}>
          Deploy Hubs Cloud on Hetzner
        </p>
        <p className="muted" style={{ margin: 0 }}>
          Guided setup · live provisioning status · secrets handoff. Runs locally on your machine.{" "}
          <Link to={INSTALLER_DOCS_PATH}>Read the installer docs</Link>
        </p>
        <div className="landing-actions">
          <Link to="/instances/new" className="btn btn-primary" style={{ textDecoration: "none" }}>
            Create new instance
          </Link>
          <Link to="/manage" className="btn btn-outline" style={{ textDecoration: "none" }}>
            Manage existing
          </Link>
        </div>
        <div className="landing-topology">
          <ClusterTopology compact />
        </div>
      </div>
    </div>
  );
}

export function ManageStub() {
  return (
    <div className="manage-stub">
      <h2>Coming soon</h2>
      <p className="muted">Management of existing clusters is not available in v1.</p>
      <Link to="/" className="btn btn-outline" style={{ marginTop: 24, textDecoration: "none" }}>
        Back to landing
      </Link>
    </div>
  );
}
