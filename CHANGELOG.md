## [0.23.5](https://github.com/AlbanAndrieu/nabla-compose/compare/0.23.4...0.23.5) (2026-09-08)


### Bug Fixes

* **pfsense:** make PHP-FPM worker validation portable ([#142](https://github.com/AlbanAndrieu/nabla-compose/issues/142)) ([27f789a](https://github.com/AlbanAndrieu/nabla-compose/commit/27f789a1594a146b146cf54be130c36928189e37))

## [0.23.4](https://github.com/AlbanAndrieu/nabla-compose/compare/0.23.3...0.23.4) (2026-09-08)


### Bug Fixes

* **pfsense:** support non-executable PHP-FPM generator ([#141](https://github.com/AlbanAndrieu/nabla-compose/issues/141)) ([a26d7fc](https://github.com/AlbanAndrieu/nabla-compose/commit/a26d7fcc16ea486120b11ba10a8fecbd3e5b6032))

## [0.23.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.23.2...0.23.3) (2026-09-08)


### Bug Fixes

* **garage:** align WebUI presentation catalog ([#140](https://github.com/AlbanAndrieu/nabla-compose/issues/140)) ([e48851b](https://github.com/AlbanAndrieu/nabla-compose/commit/e48851b2d94f66facc8959f53e014667e7fb6098))

## [0.23.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.23.1...0.23.2) (2026-09-08)


### Bug Fixes

* **truenas:** diagnose OpenRAG and refresh local sample ([#139](https://github.com/AlbanAndrieu/nabla-compose/issues/139)) ([044ab3c](https://github.com/AlbanAndrieu/nabla-compose/commit/044ab3c96cf58e1c28868eb1b0848f9031f92f3a))

## [0.23.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.23.0...0.23.1) (2026-09-08)


### Bug Fixes

* **observability:** stop cAdvisor auto-restart and plan shared services ([#137](https://github.com/AlbanAndrieu/nabla-compose/issues/137)) ([43fda83](https://github.com/AlbanAndrieu/nabla-compose/commit/43fda83f83d1ccdcd8aa55b363b24cda2006a9e7))

# [0.23.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.22.3...0.23.0) (2026-09-08)


### Features

* **keycloak:** migrate to repository runtime with shared PostgreSQL ([#136](https://github.com/AlbanAndrieu/nabla-compose/issues/136)) ([be43fef](https://github.com/AlbanAndrieu/nabla-compose/commit/be43fefc74251398376a050d17ce538530ed6958))

## [0.22.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.22.2...0.22.3) (2026-09-08)


### Bug Fixes

* **truenas:** recover missing apps and runtime compose ([#135](https://github.com/AlbanAndrieu/nabla-compose/issues/135)) ([ba858f7](https://github.com/AlbanAndrieu/nabla-compose/commit/ba858f71bcea7dac6ff266f636774770aa52ade4))

## [0.22.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.22.1...0.22.2) (2026-09-08)


### Bug Fixes

* **runtime:** recover Akvorado CrowdSec and exporter monitoring ([#134](https://github.com/AlbanAndrieu/nabla-compose/issues/134)) ([84db670](https://github.com/AlbanAndrieu/nabla-compose/commit/84db67044317dd618dffee159baae9456b24e2a0))

## [0.22.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.22.0...0.22.1) (2026-09-08)


### Bug Fixes

* **traefik:** isolate legacy DDNS updater ([#133](https://github.com/AlbanAndrieu/nabla-compose/issues/133)) ([56fa74d](https://github.com/AlbanAndrieu/nabla-compose/commit/56fa74d343417597c8717004a0982c5bd120cb91))

# [0.22.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.21.1...0.22.0) (2026-09-08)


### Features

* **ci:** add agent-first pre-build quality gate ([#132](https://github.com/AlbanAndrieu/nabla-compose/issues/132)) ([54160a8](https://github.com/AlbanAndrieu/nabla-compose/commit/54160a80344fdc139b62fb0b4af8341be6d3b2be))

## [0.21.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.21.0...0.21.1) (2026-09-07)


### Bug Fixes

* **catalog:** bind 2FAuth and Open WebUI to TrueNAS runtime ([#131](https://github.com/AlbanAndrieu/nabla-compose/issues/131)) ([2a0ecf1](https://github.com/AlbanAndrieu/nabla-compose/commit/2a0ecf149cddd875363e97a2fb1b2a48164d2445))

# [0.21.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.20.1...0.21.0) (2026-09-07)


### Features

* **k8s:** prepare FastAPI smoke, CSI preflight and infra secrets ([#130](https://github.com/AlbanAndrieu/nabla-compose/issues/130)) ([f9e508e](https://github.com/AlbanAndrieu/nabla-compose/commit/f9e508e5fde70291422eea091dc811f0d9f9d63f))

## [0.20.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.20.0...0.20.1) (2026-09-07)


### Bug Fixes

* **truenas:** stabilize Graylog and OpenRAG runtime ([#129](https://github.com/AlbanAndrieu/nabla-compose/issues/129)) ([9c77098](https://github.com/AlbanAndrieu/nabla-compose/commit/9c77098b7b85856fd083f13f9063c6dfa88834aa))

# [0.20.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.19.0...0.20.0) (2026-09-07)


### Features

* **truenas:** reconcile runtime health and service catalog ([#128](https://github.com/AlbanAndrieu/nabla-compose/issues/128)) ([292246d](https://github.com/AlbanAndrieu/nabla-compose/commit/292246d11c24de7278b119d271a584a9f180ba5f))

# [0.19.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.18.1...0.19.0) (2026-09-07)


### Features

* **access:** verify Sentry with Cloudflare Service Auth ([#125](https://github.com/AlbanAndrieu/nabla-compose/issues/125)) ([e532993](https://github.com/AlbanAndrieu/nabla-compose/commit/e532993948b9b3b8e7d187e970f912534196f9c7))

## [0.18.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.18.0...0.18.1) (2026-09-07)


### Bug Fixes

* **pfsense:** codify stabilized memory posture ([#127](https://github.com/AlbanAndrieu/nabla-compose/issues/127)) ([26ed0eb](https://github.com/AlbanAndrieu/nabla-compose/commit/26ed0eb03d1494a5a04cacd690941b6a49497710))
* **pyroscope:** persist v2 filesystem storage ([#124](https://github.com/AlbanAndrieu/nabla-compose/issues/124)) ([1d01f33](https://github.com/AlbanAndrieu/nabla-compose/commit/1d01f335504885f4de6b98c1c4310adcd69c12e1))

# [0.18.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.17.0...0.18.0) (2026-09-07)


### Bug Fixes

* **sample:** harden homelab internal dependency probes ([#123](https://github.com/AlbanAndrieu/nabla-compose/issues/123)) ([87afe76](https://github.com/AlbanAndrieu/nabla-compose/commit/87afe76af22eb6813276112f8ff411ce968c1e04))


### Features

* **mcp:** add self-hosted Sentry inspector ([#120](https://github.com/AlbanAndrieu/nabla-compose/issues/120)) ([3664d40](https://github.com/AlbanAndrieu/nabla-compose/commit/3664d40c2475a9f502487e2c044fe6525d92922d))

# [0.17.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.16.1...0.17.0) (2026-09-07)


### Features

* **pihole:** migrate native app to repository Compose ([#122](https://github.com/AlbanAndrieu/nabla-compose/issues/122)) ([7c3510c](https://github.com/AlbanAndrieu/nabla-compose/commit/7c3510c2b2608bbd06df36f3520111cdb8e51e2c))

## [0.16.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.16.0...0.16.1) (2026-09-07)


### Bug Fixes

* **sentry:** mark runtime smoke test executable ([#118](https://github.com/AlbanAndrieu/nabla-compose/issues/118)) ([4ac3259](https://github.com/AlbanAndrieu/nabla-compose/commit/4ac32592d8c69d3e8f106feaa3554a5bf0708e94))

# [0.16.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.7...0.16.0) (2026-09-07)


### Features

* **sentry:** deploy self-hosted 26.8 errors-only stack ([#117](https://github.com/AlbanAndrieu/nabla-compose/issues/117)) ([ff2232d](https://github.com/AlbanAndrieu/nabla-compose/commit/ff2232d51f037b092d1350cffed9406d4ec21fdb))

## [0.15.7](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.6...0.15.7) (2026-09-07)


### Bug Fixes

* **ntopng:** require dedicated ClickHouse identity ([#116](https://github.com/AlbanAndrieu/nabla-compose/issues/116)) ([4da44b1](https://github.com/AlbanAndrieu/nabla-compose/commit/4da44b15de0d7587315e5bb8b6a50050589b1f42))

## [0.15.6](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.5...0.15.6) (2026-09-06)


### Bug Fixes

* **langfuse:** probe container hostname for healthchecks ([#115](https://github.com/AlbanAndrieu/nabla-compose/issues/115)) ([42cf6be](https://github.com/AlbanAndrieu/nabla-compose/commit/42cf6be99f05a80290f3311c8c1180339bd42211))

## [0.15.5](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.4...0.15.5) (2026-09-06)


### Bug Fixes

* **langfuse:** grant ClickHouse ALTER SETTINGS ([#114](https://github.com/AlbanAndrieu/nabla-compose/issues/114)) ([59aeff9](https://github.com/AlbanAndrieu/nabla-compose/commit/59aeff937fe4166ef8720556aa86ecbe0a3b167d))

## [0.15.4](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.3...0.15.4) (2026-09-06)


### Bug Fixes

* **langfuse:** gate worker on runtime readiness ([#113](https://github.com/AlbanAndrieu/nabla-compose/issues/113)) ([c91f71f](https://github.com/AlbanAndrieu/nabla-compose/commit/c91f71f0021a225fc12465f99363622bf2dad862))

## [0.15.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.2...0.15.3) (2026-09-06)


### Bug Fixes

* **clickhouse:** enable SQL access management ([#112](https://github.com/AlbanAndrieu/nabla-compose/issues/112)) ([9ec56b2](https://github.com/AlbanAndrieu/nabla-compose/commit/9ec56b25138211c76d1284b1d20cc81402271045))

## [0.15.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.1...0.15.2) (2026-09-06)


### Bug Fixes

* **sample:** document and verify TrueNAS WebSocket source allowlist ([#111](https://github.com/AlbanAndrieu/nabla-compose/issues/111)) ([9a8b8cc](https://github.com/AlbanAndrieu/nabla-compose/commit/9a8b8cc3b98260d409287abceb06e4c3e47fdbd7))

## [0.15.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.15.0...0.15.1) (2026-09-06)


### Bug Fixes

* **clickhouse:** isolate Langfuse on shared database ([#110](https://github.com/AlbanAndrieu/nabla-compose/issues/110)) ([415ec3c](https://github.com/AlbanAndrieu/nabla-compose/commit/415ec3c438749a6107dbdbfb686bd63de16563d3))

# [0.15.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.14.5...0.15.0) (2026-09-06)


### Features

* **langfuse:** install v4 on fresh isolated state ([#109](https://github.com/AlbanAndrieu/nabla-compose/issues/109)) ([7f77314](https://github.com/AlbanAndrieu/nabla-compose/commit/7f77314e514c920b7ef0ef843a47de5223b7f3b1))

## [0.14.5](https://github.com/AlbanAndrieu/nabla-compose/compare/0.14.4...0.14.5) (2026-09-06)


### Bug Fixes

* **security:** keep Garage administration private ([#108](https://github.com/AlbanAndrieu/nabla-compose/issues/108)) ([d361eae](https://github.com/AlbanAndrieu/nabla-compose/commit/d361eaea1b8720e1ec3b3e376912259c6e2842aa))

## [0.14.4](https://github.com/AlbanAndrieu/nabla-compose/compare/0.14.3...0.14.4) (2026-09-06)


### Bug Fixes

* **langfuse:** document safe v4 schema rewind ([#107](https://github.com/AlbanAndrieu/nabla-compose/issues/107)) ([fd93f10](https://github.com/AlbanAndrieu/nabla-compose/commit/fd93f10e4333d301a48e89c75d531a90f001fe89))

## [0.14.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.14.2...0.14.3) (2026-09-06)


### Bug Fixes

* **security:** keep internal DNS private and remove Docker proxy exposure debt ([#106](https://github.com/AlbanAndrieu/nabla-compose/issues/106)) ([45bc9c7](https://github.com/AlbanAndrieu/nabla-compose/commit/45bc9c719582327b089f780a0233946c9816d6d8))

## [0.14.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.14.1...0.14.2) (2026-09-06)


### Bug Fixes

* **truenas:** harden runtime recovery follow-up ([#105](https://github.com/AlbanAndrieu/nabla-compose/issues/105)) ([de1edab](https://github.com/AlbanAndrieu/nabla-compose/commit/de1edab49e1ee6dd08f4f22716c4b04750d3297d))

## [0.14.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.14.0...0.14.1) (2026-09-06)


### Bug Fixes

* **ingress:** align FastAPI Sample with Cloudflare Tunnel and internal DNS ([#104](https://github.com/AlbanAndrieu/nabla-compose/issues/104)) ([059d658](https://github.com/AlbanAndrieu/nabla-compose/commit/059d658e770fffd269353961ad144124a4c59f9c))

# [0.14.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.13.0...0.14.0) (2026-09-06)


### Features

* **observability:** derive service signals from Gatus ([#102](https://github.com/AlbanAndrieu/nabla-compose/issues/102)) ([c6347b4](https://github.com/AlbanAndrieu/nabla-compose/commit/c6347b4fadc799b06438e1a53492c3b205b1f657))

# [0.13.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.12.2...0.13.0) (2026-09-06)


### Features

* **ingress:** expose FastAPI Sample through Traefik and AutoXpose DNS ([#103](https://github.com/AlbanAndrieu/nabla-compose/issues/103)) ([95e5950](https://github.com/AlbanAndrieu/nabla-compose/commit/95e595059f75ad6dd9da5dfd163224ff49545ebb))

## [0.12.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.12.1...0.12.2) (2026-09-06)


### Bug Fixes

* **observability:** harden pfSense and monitoring integration ([#97](https://github.com/AlbanAndrieu/nabla-compose/issues/97)) ([3c29215](https://github.com/AlbanAndrieu/nabla-compose/commit/3c292156fa51d4a07ec1ba0b11552be997ede945))

## [0.12.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.12.0...0.12.1) (2026-09-06)


### Bug Fixes

* **homelab:** bootstrap shared network and align pfSense policy ([#101](https://github.com/AlbanAndrieu/nabla-compose/issues/101)) ([9498a2f](https://github.com/AlbanAndrieu/nabla-compose/commit/9498a2f2869f45071f5af86c98f363772323ecd1))

# [0.12.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.11.0...0.12.0) (2026-09-06)


### Features

* **gatus:** expose synthetic service metrics ([#98](https://github.com/AlbanAndrieu/nabla-compose/issues/98)) ([6cb066a](https://github.com/AlbanAndrieu/nabla-compose/commit/6cb066abfc2de8349d068ca7b9b67e4d11e520bc))
* **talos:** harden cluster validation and network smoke ([#100](https://github.com/AlbanAndrieu/nabla-compose/issues/100)) ([9868679](https://github.com/AlbanAndrieu/nabla-compose/commit/98686799b31d8ef466e7d006aec2cf833d58cd2e))

# [0.11.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.10.1...0.11.0) (2026-09-06)


### Features

* **catalog:** add NIST CSF security function contract ([#96](https://github.com/AlbanAndrieu/nabla-compose/issues/96)) ([0f55a70](https://github.com/AlbanAndrieu/nabla-compose/commit/0f55a70748d1f4f837a1787ba1dc477b5ea0d198))

## [0.10.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.10.0...0.10.1) (2026-09-06)


### Bug Fixes

* **talos:** preserve cluster validator executable mode ([#93](https://github.com/AlbanAndrieu/nabla-compose/issues/93)) ([9fdc0e6](https://github.com/AlbanAndrieu/nabla-compose/commit/9fdc0e6ced1e1298895a2ccc1c3552d8f1e1b87d))
* **talos:** restore validator executable bit ([#92](https://github.com/AlbanAndrieu/nabla-compose/issues/92)) ([75481d5](https://github.com/AlbanAndrieu/nabla-compose/commit/75481d5246ea4536ee5cc81615d5a23f171f4802))

# [0.10.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.9.0...0.10.0) (2026-09-06)


### Features

* **catalog:** add service role and criticality contract ([#91](https://github.com/AlbanAndrieu/nabla-compose/issues/91)) ([ad1fb4d](https://github.com/AlbanAndrieu/nabla-compose/commit/ad1fb4d011074b9d515d82457b52ab9294141391))

# [0.9.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.8.0...0.9.0) (2026-09-06)


### Features

* **observability:** monitor TrueNAS and harden Talos health ([#90](https://github.com/AlbanAndrieu/nabla-compose/issues/90)) ([0fed760](https://github.com/AlbanAndrieu/nabla-compose/commit/0fed760598fc3d64e9efd476b0a69c42dbf05408))

# [0.8.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.7.0...0.8.0) (2026-09-06)


### Features

* **talos:** continue cluster bootstrap and homelab hardening ([#87](https://github.com/AlbanAndrieu/nabla-compose/issues/87)) ([3776860](https://github.com/AlbanAndrieu/nabla-compose/commit/37768600ea2a411af2d4274bc0621e0293c72de0))

# [0.7.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.6.0...0.7.0) (2026-09-05)


### Features

* **sample:** harden TrueNAS local runtime dependencies ([#89](https://github.com/AlbanAndrieu/nabla-compose/issues/89)) ([727be01](https://github.com/AlbanAndrieu/nabla-compose/commit/727be01bd2dd8c9c78a0f863ad311f0459b90fcd))

# [0.6.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.5.0...0.6.0) (2026-09-05)


### Features

* **sample:** add local FastAPI Sample deployment ([#88](https://github.com/AlbanAndrieu/nabla-compose/issues/88)) ([da54c6d](https://github.com/AlbanAndrieu/nabla-compose/commit/da54c6d920d1f89e8db0c4501366ebc0fc80e354))

# [0.5.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.4.0...0.5.0) (2026-09-05)


### Features

* **observability:** centralize pfSense and application logs ([#85](https://github.com/AlbanAndrieu/nabla-compose/issues/85)) ([e561ab5](https://github.com/AlbanAndrieu/nabla-compose/commit/e561ab5a6565519acf274f89065f2dc2f7d2a243))

# [0.4.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.3.2...0.4.0) (2026-09-05)


### Features

* **talos:** prepare TrueNAS Kubernetes bootstrap ([#86](https://github.com/AlbanAndrieu/nabla-compose/issues/86)) ([244412e](https://github.com/AlbanAndrieu/nabla-compose/commit/244412eeeb4e1bcf8a6f7eb4bf0f3256bc22499f))

## [0.3.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.3.1...0.3.2) (2026-09-05)


### Bug Fixes

* **garage:** align bootstrap env and admin preflight ([#84](https://github.com/AlbanAndrieu/nabla-compose/issues/84)) ([64632f5](https://github.com/AlbanAndrieu/nabla-compose/commit/64632f59337a52876784349c1917c87715376bcf))

## [0.3.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.3.0...0.3.1) (2026-09-05)


### Bug Fixes

* **state:** make Garage backend bootstrap safe ([#83](https://github.com/AlbanAndrieu/nabla-compose/issues/83)) ([6f8b95d](https://github.com/AlbanAndrieu/nabla-compose/commit/6f8b95dbd3ce1098e438e417e85a270ab7f85844))

# [0.3.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.2.0...0.3.0) (2026-09-03)


### Features

* **catalog:** emit authoritative runtime placement ([#81](https://github.com/AlbanAndrieu/nabla-compose/issues/81)) ([f459cb8](https://github.com/AlbanAndrieu/nabla-compose/commit/f459cb809de62fc75dd980f2c45082b3f42bfefa))

# [0.2.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.1.1...0.2.0) (2026-09-03)


### Features

* **catalog:** add hostedBy placement relation capability ([#80](https://github.com/AlbanAndrieu/nabla-compose/issues/80)) ([1e2d946](https://github.com/AlbanAndrieu/nabla-compose/commit/1e2d9465b0ee773bb588ac73cefd84f9c9582d8e))

## [0.1.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.1.0...0.1.1) (2026-09-01)


### Bug Fixes

* **garage:** make Traefik ingress topology authoritative ([#75](https://github.com/AlbanAndrieu/nabla-compose/issues/75)) ([6c08a81](https://github.com/AlbanAndrieu/nabla-compose/commit/6c08a81467a3f483651d53212cf0297bb8afa38e))

# [0.1.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.0.1...0.1.0) (2026-09-01)


### Features

* **infra:** stabilize Garage, TrueNAS and Talos bootstrap ([#73](https://github.com/AlbanAndrieu/nabla-compose/issues/73)) ([8233a78](https://github.com/AlbanAndrieu/nabla-compose/commit/8233a78850166de4e3ccdf2eb92ae6ca3fa2921b))

## [0.0.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.0.0...0.0.1) (2026-08-30)


### Bug Fixes

* **release:** bootstrap 0.0.1 semantic release ([#72](https://github.com/AlbanAndrieu/nabla-compose/issues/72)) ([c4de831](https://github.com/AlbanAndrieu/nabla-compose/commit/c4de8315d6cf6931d42ebe3d8419bf8700b49dfd))

# Changelog

All notable changes to `nabla-compose` are recorded here by semantic-release from Conventional Commits.

The first automated GitHub release is bootstrapped as `0.0.1`.
