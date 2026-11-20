# Identifiers (not secrets) of mail.tofu, read on 20/11/2026 with GET only.
# Kept apart from import-ids.auto.tfvars, which capture-homelab-tofu.sh rewrites.
albanandrieu_zone_id = "227e423f0194d42016dd753d4a23437f" # gitleaks:allow

mail_spf_record_ids = {
  "albandrieu.com"   = "62df67144fc68601714221ea9052563c" # gitleaks:allow
  "albanandrieu.com" = "c1311131de9a7769f01a05d0d858e09c" # gitleaks:allow
}
