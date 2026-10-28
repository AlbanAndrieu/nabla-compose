# POSIX awk; read-only. Accept -v frontend=main_Web_HTTPS.
# Deliberately omit bindings, certificate directives, headers and backend secrets.
BEGIN {
  found = 0
  emitted = 0
  backend_found = 0
  backend_servers = 0
}
$1 == "frontend" || $1 == "listen" || $1 == "backend" {
  active = ($1 == "frontend" && $2 == frontend)
  backend_active = (backend_name != "" && $1 == "backend" && $2 == backend_name)
  if (active) {
    found = 1
    printf "frontend=%s line=%d\n", $2, NR
  }
  if (backend_active) {
    backend_found = 1
    printf "backend=%s line=%d\n", $2, NR
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
  if ($3 == "if" && $4 == "nexus") {
    # This reports a declared route, not proof it received WAN traffic.
    printf "nexus_declared_backend=%s\n", $2
  }
  emitted++
  next
}
active && $1 == "default_backend" {
  printf "line=%d type=default_backend %s\n", NR, $0
  emitted++
  next
}
# Optional backend inspection prints ONLY named server and address/port.
# Do not print full server lines: they can contain sensitive options.
backend_active && $1 == "mode" {
  if ($2 == "http" || $2 == "tcp") printf "backend_mode=%s\n", $2
  next
}
backend_active && $1 == "server" {
  backend_servers++
  target = $3
  if (length(target) > 160 || target ~ /[=@\/?#]/) target = "<redacted>"
  printf "backend_server=%s target=%s\n", $2, target
  next
}
END {
  if (!found) {
    printf "ERROR: frontend '%s' not found; no ACL conclusion possible\n", frontend
    exit 3
  }
  printf "frontend_rules_sampled=%d\n", emitted
  if (backend_name != "") {
    if (!backend_found) {
      printf "ERROR: backend '%s' not found; backend target unknown\n", backend_name
      exit 4
    }
    if (!backend_servers) print "backend_target=NOT_OBSERVED"
  }
  print "wan_rejection=NOT_VERIFIED (configuration sample only)"
}
