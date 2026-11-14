# Obsolete Garage pilot: disabled

Do not run Terragrunt here. The H16 Entra identity lab has its OWN state
backend in terraform/entra-id-lab/backend.tofu (Azure Blob native lease).
This avoids two writers from separate backends managing identical Entra objects.
No cloud apply was performed with the original Garage configuration.
