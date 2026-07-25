variable "hcloud_token" {
  sensitive = true
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key"
  type        = string
}

variable "ssh_private_key_path" {
  description = "Path to the SSH private key"
  type        = string
}

variable "k3s_token" {
  description = "K3s cluster token for node authentication"
  type        = string
  sensitive   = true
}

variable "location" {
  description = "Hetzner datacenter location"
  type        = string
  default     = "nbg1"
}

variable "master_server_type" {
  type    = string
  default = "cpx13"
}

variable "webrtc_server_type" {
  type    = string
  default = "cx23"
}

variable "web_server_type" {
  type    = string
  default = "cx23"
}

variable "estimated_monthly_cost_eur" {
  type        = string
  default     = ""
  description = "Gross monthly cost estimate for the three servers (EUR), filled at render time from Hetzner API"
}

variable "firewall_hardened" {
  type        = bool
  default     = false
  description = "When true, restrict inbound firewall to HCCE-required ports only"
}

variable "firewall_allow_ssh" {
  type        = bool
  default     = true
  description = "When hardened, allow inbound TCP 22 for direct SSH to nodes"
}
