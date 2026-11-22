// Node preload for scripts/mcp/truenas-readonly.sh: resolve one hostname to a
// fixed LAN address so TLS still verifies the real certificate name.
// truenas.albandrieu.com resolves to the Cloudflare Tunnel on the workstation,
// and the TrueNAS certificate covers no LAN-only name. Other names are untouched.
import dns from "node:dns";

const host = process.env.NABLA_PIN_HOST;
const addr = process.env.NABLA_PIN_ADDR;

if (host && addr) {
  const family = addr.includes(":") ? 6 : 4;
  const original = dns.lookup;
  dns.lookup = function pinnedLookup(name, options, callback) {
    if (typeof options === "function") {
      callback = options;
      options = {};
    }
    if (typeof options === "number") options = { family: options };
    if (name !== host) return original.call(dns, name, options, callback);
    const all = Boolean(options && options.all);
    return process.nextTick(() =>
      all
        ? callback(null, [{ address: addr, family }])
        : callback(null, addr, family),
    );
  };
}
