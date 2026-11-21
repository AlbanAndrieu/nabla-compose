# Identifiers (not secrets) of mail.tofu, read on 20/11/2026 with GET only.
# Kept apart from import-ids.auto.tfvars, which capture-homelab-tofu.sh rewrites.
albanandrieu_zone_id = "227e423f0194d42016dd753d4a23437f" # gitleaks:allow

mail_spf_record_ids = {
  "albandrieu.com"   = "62df67144fc68601714221ea9052563c" # gitleaks:allow
  "albanandrieu.com" = "c1311131de9a7769f01a05d0d858e09c" # gitleaks:allow
}

mail_zone_ids = {
  "bababou.com"  = "61e2a1b07b61809660ad83963e0dbfd7" # gitleaks:allow
  "bababou.net"  = "48c393f5dffe3a739bf5fa81d99e04e2" # gitleaks:allow
  "dr-alban.com" = "6c5ccf0f43895850f2262065b664ab72" # gitleaks:allow
  "eokoo.net"    = "07ca4cfe51a5b10def541febe5ac1ace" # gitleaks:allow
  "eokou.com"    = "9427a9c671638c8249c8f8c090362058" # gitleaks:allow
  "heoko.com"    = "648218864bdc5fdf92b73840a544def9" # gitleaks:allow
  "heoko.net"    = "e4e96ff74d4f12eaf0c30e03d364175c" # gitleaks:allow
  "heoko.org"    = "06a2809d003c34336d76bb402cb93b07" # gitleaks:allow
  "heokoo.com"   = "078c0f7f56ca145ef89b6a4388714b7d" # gitleaks:allow
  "heokoo.net"   = "12a862545b7c573bedb6fa28027ab905" # gitleaks:allow
  "heokoo.org"   = "6d03cc839c5802d93a55c45db801ff84" # gitleaks:allow
  "heokou.com"   = "47014dfc9c86ab81020f62f493f4eba7" # gitleaks:allow
  "heokou.net"   = "06062693b866586d19c301030fc04aa7" # gitleaks:allow
  "heokou.org"   = "54792692fe4c1fdaa3e530ce178f8534" # gitleaks:allow
  "papapou.com"  = "c09a7fad9b8c2ad7ce8aeb746265561b" # gitleaks:allow
  "papapou.net"  = "2e1e665ff148873b590b847aec301b8c" # gitleaks:allow
  "papapou.org"  = "48a9ea64322b4796d05850a7709fdf9e" # gitleaks:allow
  "papoyou.net"  = "29119681fa1071f1271bd4974f02baae" # gitleaks:allow
}

mail_dmarc_record_ids = {
  "albandrieu.com"   = "b5577d304e3b9372255f1ce91298ab5f" # gitleaks:allow
  "albanandrieu.com" = "1e3d3d57b8a30e0c4c749a7c058ae39e" # gitleaks:allow
  "bababou.com"      = "254449068392c81a043dea97f1f568be" # gitleaks:allow
  "dr-alban.com"     = "f9cdbd6a2aec1052e789d7c6d63f44c8" # gitleaks:allow
}
