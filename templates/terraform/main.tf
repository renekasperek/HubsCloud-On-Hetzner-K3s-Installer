terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "1.50.0"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

resource "hcloud_network" "private_network" {
  name     = "kubernetes-cluster"
  ip_range = "10.0.0.0/16"
}

resource "hcloud_network_subnet" "private_network_subnet" {
  type         = "cloud"
  network_id   = hcloud_network.private_network.id
  network_zone = "eu-central"
  ip_range     = "10.0.1.0/24"
}

resource "hcloud_ssh_key" "h_cloud_rsa" {
  name       = "h_cloud_key"
  public_key = file(var.ssh_public_key_path)
}

resource "hcloud_placement_group" "my_group" {
  name = "kubernetes-group"
  type = "spread"
}

resource "hcloud_firewall" "open_firewall" {
  name = var.firewall_hardened ? "hcce-hardened-firewall" : "open-firewall"

  dynamic "rule" {
    for_each = var.firewall_hardened ? [
      for port in ["80", "443", "6443", "4443", "5349", "31621", "32471"] : {
        direction  = "in"
        protocol   = "tcp"
        port       = port
        source_ips = ["0.0.0.0/0", "::/0"]
      }
      ] : [
      {
        direction  = "in"
        protocol   = "tcp"
        port       = "1-65535"
        source_ips = ["0.0.0.0/0", "::/0"]
      }
    ]
    content {
      direction  = rule.value.direction
      protocol   = rule.value.protocol
      port       = rule.value.port
      source_ips = rule.value.source_ips
    }
  }

  dynamic "rule" {
    for_each = var.firewall_hardened ? [
      {
        direction  = "in"
        protocol   = "udp"
        port       = "35000-60000"
        source_ips = ["0.0.0.0/0", "::/0"]
      }
      ] : [
      {
        direction  = "in"
        protocol   = "udp"
        port       = "1-65535"
        source_ips = ["0.0.0.0/0", "::/0"]
      }
    ]
    content {
      direction  = rule.value.direction
      protocol   = rule.value.protocol
      port       = rule.value.port
      source_ips = rule.value.source_ips
    }
  }

  dynamic "rule" {
    for_each = var.firewall_hardened ? [] : [
      {
        direction  = "in"
        protocol   = "icmp"
        source_ips = ["0.0.0.0/0", "::/0"]
      }
    ]
    content {
      direction  = rule.value.direction
      protocol   = rule.value.protocol
      source_ips = rule.value.source_ips
    }
  }

  dynamic "rule" {
    for_each = var.firewall_hardened && var.firewall_allow_ssh ? [
      {
        direction  = "in"
        protocol   = "tcp"
        port       = "22"
        source_ips = ["0.0.0.0/0", "::/0"]
      }
    ] : []
    content {
      direction  = rule.value.direction
      protocol   = rule.value.protocol
      port       = rule.value.port
      source_ips = rule.value.source_ips
    }
  }
}

resource "hcloud_server" "master_node" {
  name               = "hcce-master-db"
  image              = "ubuntu-24.04"
  server_type        = var.master_server_type
  location           = var.location
  ssh_keys           = [hcloud_ssh_key.h_cloud_rsa.id]
  placement_group_id = hcloud_placement_group.my_group.id
  firewall_ids       = [hcloud_firewall.open_firewall.id]

  labels = {
    role     = "master"
    workload = "database-haproxy"
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  network {
    network_id = hcloud_network.private_network.id
    ip         = "10.0.1.1"
  }

  user_data = templatefile("${path.module}/cloud-init-master.yaml", {
    k3s_token      = var.k3s_token
    ssh_public_key = chomp(file(var.ssh_public_key_path))
  })

  # The hcloud provider never writes `location` back into state (it stays ""
  # on every server, on every instance we have ever created), while the config
  # always sets it. Because `location` is ForceNew, that permanent diff makes
  # EVERY apply want to destroy and recreate all three servers — which is how
  # firewall hardening once wiped a running cluster.
  #
  # A server's location cannot be changed in place; Hetzner has no move
  # operation. So a genuine location change can only be realised by an explicit
  # destroy + create, never by an in-place apply. Ignoring it here is therefore
  # safe, and does NOT affect server_type: resizing still replaces as expected.
  lifecycle {
    ignore_changes = [location]
  }

  depends_on = [
    hcloud_network_subnet.private_network_subnet,
    hcloud_firewall.open_firewall,
    hcloud_placement_group.my_group,
    hcloud_ssh_key.h_cloud_rsa
  ]
}

resource "hcloud_server" "webrtc_worker" {
  name               = "hcce-webrtc-worker"
  image              = "ubuntu-24.04"
  server_type        = var.webrtc_server_type
  location           = var.location
  ssh_keys           = [hcloud_ssh_key.h_cloud_rsa.id]
  placement_group_id = hcloud_placement_group.my_group.id
  firewall_ids       = [hcloud_firewall.open_firewall.id]

  labels = {
    role     = "worker"
    workload = "webrtc"
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  network {
    network_id = hcloud_network.private_network.id
    ip         = "10.0.1.2"
  }

  user_data = templatefile("${path.module}/cloud-init-webrtc-worker.yaml", {
    k3s_token      = var.k3s_token
    ssh_public_key = chomp(file(var.ssh_public_key_path))
  })

  # The hcloud provider never writes `location` back into state (it stays ""
  # on every server, on every instance we have ever created), while the config
  # always sets it. Because `location` is ForceNew, that permanent diff makes
  # EVERY apply want to destroy and recreate all three servers — which is how
  # firewall hardening once wiped a running cluster.
  #
  # A server's location cannot be changed in place; Hetzner has no move
  # operation. So a genuine location change can only be realised by an explicit
  # destroy + create, never by an in-place apply. Ignoring it here is therefore
  # safe, and does NOT affect server_type: resizing still replaces as expected.
  lifecycle {
    ignore_changes = [location]
  }

  depends_on = [
    hcloud_server.master_node,
    hcloud_network_subnet.private_network_subnet,
    hcloud_firewall.open_firewall,
    hcloud_placement_group.my_group,
    hcloud_ssh_key.h_cloud_rsa
  ]
}

# Web worker starts after webrtc worker so cloud-init joins are staggered (master must be ready first).
resource "hcloud_server" "web_worker" {
  name               = "hcce-web-worker"
  image              = "ubuntu-24.04"
  server_type        = var.web_server_type
  location           = var.location
  ssh_keys           = [hcloud_ssh_key.h_cloud_rsa.id]
  placement_group_id = hcloud_placement_group.my_group.id
  firewall_ids       = [hcloud_firewall.open_firewall.id]

  labels = {
    role     = "worker"
    workload = "web"
  }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  network {
    network_id = hcloud_network.private_network.id
    ip         = "10.0.1.3"
  }

  user_data = templatefile("${path.module}/cloud-init-web-worker.yaml", {
    k3s_token      = var.k3s_token
    ssh_public_key = chomp(file(var.ssh_public_key_path))
  })

  # The hcloud provider never writes `location` back into state (it stays ""
  # on every server, on every instance we have ever created), while the config
  # always sets it. Because `location` is ForceNew, that permanent diff makes
  # EVERY apply want to destroy and recreate all three servers — which is how
  # firewall hardening once wiped a running cluster.
  #
  # A server's location cannot be changed in place; Hetzner has no move
  # operation. So a genuine location change can only be realised by an explicit
  # destroy + create, never by an in-place apply. Ignoring it here is therefore
  # safe, and does NOT affect server_type: resizing still replaces as expected.
  lifecycle {
    ignore_changes = [location]
  }

  depends_on = [
    hcloud_server.master_node,
    hcloud_server.webrtc_worker,
    hcloud_network_subnet.private_network_subnet,
    hcloud_firewall.open_firewall,
    hcloud_placement_group.my_group,
    hcloud_ssh_key.h_cloud_rsa
  ]
}
