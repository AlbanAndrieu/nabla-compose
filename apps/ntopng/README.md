# ntopng

The service captures the host interface configured by `NTOPNG_INTERFACE` and
uses the existing ClickHouse server for historical flows.

The ClickHouse integration requires an **ntopng Enterprise M or higher**
license. Place the license in the container using the TrueNAS application
configuration if that feature is enabled.

Default ClickHouse target: `172.17.0.24:9000`, database `ntopng`.
