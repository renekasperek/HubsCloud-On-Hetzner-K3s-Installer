output "master_node_ip" {
  value       = hcloud_server.master_node.ipv4_address
  description = "Public IP of the master node (database + haproxy)"
}

output "webrtc_worker_ip" {
  value       = hcloud_server.webrtc_worker.ipv4_address
  description = "Public IP of the WebRTC worker node"
}

output "web_worker_ip" {
  value       = hcloud_server.web_worker.ipv4_address
  description = "Public IP of the web worker node"
}

output "private_network_id" {
  value       = hcloud_network.private_network.id
  description = "ID of the private network"
}

output "private_network_subnet" {
  value       = hcloud_network_subnet.private_network_subnet.ip_range
  description = "IP range of the private network subnet"
}

output "cluster_info" {
  value = {
    master_node = {
      name        = hcloud_server.master_node.name
      public_ip   = hcloud_server.master_node.ipv4_address
      private_ip  = "10.0.1.1"
      workload    = "database-haproxy"
      server_type = var.master_server_type
    }
    webrtc_worker = {
      name        = hcloud_server.webrtc_worker.name
      public_ip   = hcloud_server.webrtc_worker.ipv4_address
      private_ip  = "10.0.1.2"
      workload    = "webrtc"
      server_type = var.webrtc_server_type
    }
    web_worker = {
      name        = hcloud_server.web_worker.name
      public_ip   = hcloud_server.web_worker.ipv4_address
      private_ip  = "10.0.1.3"
      workload    = "web"
      server_type = var.web_server_type
    }
  }
  description = "Complete cluster information"
}

output "ssh_commands" {
  value = {
    master_node   = "ssh cluster@${hcloud_server.master_node.ipv4_address}"
    webrtc_worker = "ssh cluster@${hcloud_server.webrtc_worker.ipv4_address}"
    web_worker    = "ssh cluster@${hcloud_server.web_worker.ipv4_address}"
  }
  description = "SSH commands to access each node"
}

output "deployment_instructions" {
  value       = <<EOT
  Multi-node K3s cluster deployment completed!

  Architecture:
  - Master Node (${hcloud_server.master_node.name}): Database + HAProxy + API
  - WebRTC Worker (${hcloud_server.webrtc_worker.name}): Dialog + Coturn (hostNetwork)
  - Web Worker (${hcloud_server.web_worker.name}): Hubs + Spoke + Image Processing

  Next steps:
  1. Verify cluster: ssh cluster@${hcloud_server.master_node.ipv4_address} 'kubectl get nodes -o wide'
  2. Deploy HCCE: kubectl apply -f k3s-setup/hcce/hcce-multinode.yaml
  3. Deploy HAProxy: kubectl apply -f k3s-setup/haproxy/
  4. Deploy metrics-server: kubectl apply -f k3s-setup/metrics-server/

  WebRTC ports (hostNetwork):
  - Dialog: 4443 (on ${hcloud_server.webrtc_worker.ipv4_address})
  - Coturn: 5349 (on ${hcloud_server.webrtc_worker.ipv4_address})

  Server types (${var.location}):
  - Master: ${var.master_server_type}
  - WebRTC: ${var.webrtc_server_type}
  - Web: ${var.web_server_type}
  Estimated gross monthly (3 servers): ${var.estimated_monthly_cost_eur != "" ? "€${var.estimated_monthly_cost_eur}" : "not computed — see hetzner.com/pricing"}
  (Load balancer and volumes are additional.)
  EOT
  description = "Deployment instructions and next steps"
}
