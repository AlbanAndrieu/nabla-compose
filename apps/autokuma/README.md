# AutoKuma generated monitors

`static/generated.json` is an AutoKuma static-file source generated from the Compose services in `apps/`.

Mount `static/` into AutoKuma and configure `AUTOKUMA__STATIC_MONITORS` to that directory. HTTP services generate `http` monitors; published non-HTTP/unknown services generate `port` monitors.

This repository deliberately uses AutoKuma files instead of adding `kuma.*` labels to every Compose service.
