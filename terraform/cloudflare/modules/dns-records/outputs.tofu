output "retired_record_keys" {
  description = "Retired records kept in configuration (adopt phase only)."
  value       = keys(local.retired_records)
}
