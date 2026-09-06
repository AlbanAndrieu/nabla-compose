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
