variable "grafana_url" {
  description = "Grafana base URL on the LAN (no internal TLS route exists for Grafana)."
  type        = string
  default     = "http://172.17.0.24:30037"
}
