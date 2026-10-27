# POSIX awk; read-only. Accept -v frontend=main_Web_HTTPS.
# Deliberately omit bindings, certificate directives, headers and backend secrets.
BEGIN {
  found = 0
  emitted = 0
}
$1 == "frontend" || $1 == "listen" || $1 == "backend" {
  active = ($1 == "frontend" && $2 == frontend)
  if (active) {
    found = 1
    printf "frontend=%s line=%d\n", $2, NR
  }
  next
}
active && $1 == "acl" {
  if ($2 == "int" || $2 ~ /^aclcrt_/ || $2 ~ /nexus/ || index($0, "txn.txnhost") != 0) {
    printf "line=%d type=acl %s\n", NR, $0
    emitted++
  }
  next
}
active && $1 == "http-request" {
  if ($2 == "deny" || $2 == "return" || $2 == "allow" || $2 ~ /^set-var\(txn\.txnhost\)/) {
    printf "line=%d type=http_rule %s\n", NR, $0
    emitted++
  }
  next
}
active && $1 == "tcp-request" {
  if ($2 == "content" || $2 == "connection") {
    printf "line=%d type=tcp_rule %s\n", NR, $0
    emitted++
  }
  next
}
active && $1 == "use_backend" {
  printf "line=%d type=backend_route %s\n", NR, $0
  emitted++
  next
}
active && $1 == "default_backend" {
  printf "line=%d type=default_backend %s\n", NR, $0
  emitted++
  next
}
END {
  if (!found) {
    printf "ERROR: frontend '%s' not found; no ACL conclusion possible\n", frontend
    exit 3
  }
  printf "frontend_rules_sampled=%d\n", emitted
  print "wan_rejection=NOT_VERIFIED (configuration sample only)"
}
