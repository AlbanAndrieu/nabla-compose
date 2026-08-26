# Gatus generated endpoints

`generated-endpoints.yaml` is generated from the Compose services in `apps/`.

Generation policy:

- an explicit `x-nabla.url` or Traefik host rule becomes an HTTP endpoint;
- otherwise, a non-loopback published port becomes a TCP endpoint;
- services with neither are reported but not probed.

The TCP fallback intentionally checks connectivity only; it does not pretend that every published service exposes an HTTP health route.
