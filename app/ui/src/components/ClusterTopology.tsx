export type ClusterTopologyProps = {
  compact?: boolean;
};

const MASTER_WORKLOADS = [
  "PostgreSQL",
  "PgBouncer",
  "Reticulum",
  "HAProxy Ingress controller",
  "pgsql-backup (CronJob)",
];

const WEB_WORKLOADS = ["Hubs", "Spoke", "Nearspark", "Photomnemonic"];

const WEBRTC_WORKLOADS = ["Dialog", "Coturn"];

const MASTER_VOLUMES = ["pgsql-pvc", "pgsql-backups-pvc", "ret-pvc"];

function NodeCard({
  title,
  role,
  extra,
  workloads,
  volumes,
  volumeNote,
  footnote,
}: {
  title: string;
  role: string;
  extra?: string;
  workloads: string[];
  volumes?: string[];
  volumeNote?: string;
  footnote?: string;
}) {
  return (
    <article className="topo-node">
      <header className="topo-node-head">
        <h4 className="topo-node-title">{title}</h4>
        <p className="topo-node-role">
          <span className="topo-label">workload-type:</span> {role}
        </p>
        {extra ? <p className="topo-node-extra">{extra}</p> : null}
      </header>
      <div className="topo-node-section">
        <p className="topo-section-label">Workloads</p>
        <ul className="topo-list">
          {workloads.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </div>
      <div className="topo-node-section">
        <p className="topo-section-label">Volumes</p>
        {volumes && volumes.length > 0 ? (
          <ul className="topo-list topo-volumes">
            {volumes.map((name) => (
              <li key={name}>
                <span className="topo-disk" aria-hidden>
                  ◐
                </span>
                {name}
              </li>
            ))}
          </ul>
        ) : (
          <p className="topo-muted">{volumeNote || "No persistent volumes"}</p>
        )}
        {footnote ? <p className="topo-footnote">{footnote}</p> : null}
      </div>
    </article>
  );
}

/** Fixed architecture diagram — server types and volume sizes are wizard choices, not shown here. */
export function ClusterTopology({ compact = false }: ClusterTopologyProps) {
  return (
    <div className={`cluster-topology${compact ? " is-compact" : ""}`} aria-label="Cluster architecture">
      <div className="topo-ingress">
        <div className="topo-ingress-box">Hetzner Load Balancer</div>
        <div className="topo-connector" aria-hidden />
        <div className="topo-ingress-box topo-ingress-platform">
          HAProxy Ingress
          <span className="topo-ingress-sub">cert-manager (TLS)</span>
        </div>
      </div>
      <p className="topo-traffic-caption">
        Traffic: Internet → Hetzner LB → HAProxy → your hub domain (Let&apos;s Encrypt via cert-manager)
      </p>
      <div className="topo-nodes">
        <NodeCard
          title="Master"
          role="database"
          extra="k3s control-plane"
          workloads={MASTER_WORKLOADS}
          volumes={MASTER_VOLUMES}
        />
        <NodeCard
          title="Web worker"
          role="web"
          workloads={WEB_WORKLOADS}
          volumeNote="No persistent volumes on this node"
        />
        <NodeCard
          title="WebRTC worker"
          role="webrtc"
          workloads={WEBRTC_WORKLOADS}
          volumeNote="No persistent volumes on this node"
          footnote="Dialog & Coturn use hostNetwork for UDP/TCP ports"
        />
      </div>
    </div>
  );
}
