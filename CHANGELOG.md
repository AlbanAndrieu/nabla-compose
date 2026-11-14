## [0.84.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.84.0...0.84.1) (2026-11-14)


### Bug Fixes

* **g1:** reject ambiguous cron enabled status and date receipt after restore [skip ci] ([cd6ba9d](https://github.com/AlbanAndrieu/nabla-compose/commit/cd6ba9decac833ac7a2ecc5a4ff5982df99b2365))
* **postgresbackup:** require fresh restore receipt before cron activation; track pfSense gaps [skip ci] ([19b14e7](https://github.com/AlbanAndrieu/nabla-compose/commit/19b14e7bcd4729afddb9697d9b1f804ae6bc55eb))

# [0.84.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.83.0...0.84.0) (2026-11-14)


### Features

* **catalog:** project the Compose runtime binding into entities.json ([959dceb](https://github.com/AlbanAndrieu/nabla-compose/commit/959dceb68742769487262fb9f4a1f42ab1632d63))

# [0.83.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.82.0...0.83.0) (2026-11-14)


### Features

* **litellm:** one GPU model, add qwen-think, drop llama3.2 and gemma3 [skip ci] ([22ad3fe](https://github.com/AlbanAndrieu/nabla-compose/commit/22ad3fecc26f5502a474bbc7b2dbc7987a0b4092))
* **litellm:** serve rr-json with bonsai-2:9b, shared with qwen [skip ci] ([ae29fcf](https://github.com/AlbanAndrieu/nabla-compose/commit/ae29fcfac3be0139cc0730cfe2269ca09ee6e6ed))

# [0.82.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.81.0...0.82.0) (2026-11-13)


### Bug Fixes

* **pfsense:** flag Snort posture drift and CrowdSec Small reversal ([531d912](https://github.com/AlbanAndrieu/nabla-compose/commit/531d91288aa843c175c5f849fa134330f3315006))


### Features

* **pfsense:** check and apply the Netgate 1100 posture over SSH ([7810da6](https://github.com/AlbanAndrieu/nabla-compose/commit/7810da62dbd0c840e65886e4dc1577024ee81d9c))

# [0.81.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.80.0...0.81.0) (2026-11-13)


### Features

* **litellm:** serve qwen with bonsai-2:9b on the workstation GPU [skip ci] ([956f4b0](https://github.com/AlbanAndrieu/nabla-compose/commit/956f4b0062690665b71d87eaa4b01f2c4c7f8d12))

# [0.80.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.79.0...0.80.0) (2026-11-13)


### Bug Fixes

* **litellm:** drop the three TrueNAS routes whose models are gone ([18293fa](https://github.com/AlbanAndrieu/nabla-compose/commit/18293fab5ea340cc5ec510cd3c5b84d0bd8e3e54))
* **redis:** refuse to start the workstation Redis without REDIS_AUTH ([a5c58b1](https://github.com/AlbanAndrieu/nabla-compose/commit/a5c58b1a75fb40aee025243b4a64ccd12f72eb11))
* **scripts:** make the postgres restore proof executable ([8dbe4dc](https://github.com/AlbanAndrieu/nabla-compose/commit/8dbe4dcb99847093d2f93e6eee4db52e227c5216))


### Features

* **prometheus:** alert on worn or failing workstation disks ([034d1df](https://github.com/AlbanAndrieu/nabla-compose/commit/034d1dff8253dc0849b2f4fc44091095d958f73a))

# [0.79.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.78.1...0.79.0) (2026-11-13)


### Bug Fixes

* **homarr:** send a JSON body when setting the home board ([b35db22](https://github.com/AlbanAndrieu/nabla-compose/commit/b35db22a71000bd3699386a09945ff2f95b4b8a0))


### Features

* **g1:** rebase restore proof on compacted H01-H19 roadmap [skip ci] ([fae19f2](https://github.com/AlbanAndrieu/nabla-compose/commit/fae19f256bb9ecc2b039e5a49a516237b86a1f67))

## [0.78.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.78.0...0.78.1) (2026-11-13)


### Bug Fixes

* **csi:** fail closed on stale controller rollout evidence [skip ci] ([1b500ba](https://github.com/AlbanAndrieu/nabla-compose/commit/1b500ba63581e7b9de548f64b1da9612a7b69f6a))

# [0.78.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.77.0...0.78.0) (2026-11-13)


### Bug Fixes

* **truenas:** repair homarr-sync layouts, clamd OOM and bitcoind health ([2feee5f](https://github.com/AlbanAndrieu/nabla-compose/commit/2feee5f256a56c4da93418b7a756ed3fb9f728da))


### Features

* **catalog:** cut the service catalog over to V2 exposure intent ([13aa9dd](https://github.com/AlbanAndrieu/nabla-compose/commit/13aa9dd97a128a9f80260a6ae75dba32ef32366b))
* **cloudflare:** apply the 13/11 exposure decisions to the V2 intent ([0b9dc53](https://github.com/AlbanAndrieu/nabla-compose/commit/0b9dc53abe71e2176e88672b9bb8455f980213ef))

# [0.77.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.76.1...0.77.0) (2026-11-13)


### Features

* **pfsense:** prepare 26.07 upgrade preflight ([4ac24bb](https://github.com/AlbanAndrieu/nabla-compose/commit/4ac24bb6ae30a4b9fad4784c00db3f21189c7d43))

## [0.76.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.76.0...0.76.1) (2026-11-13)


### Bug Fixes

* **catalog:** mark CrowdSec, DSOMM, n8n and Akvorado active ([727745a](https://github.com/AlbanAndrieu/nabla-compose/commit/727745a3afac72b59d3a629e07bfaf1a1c7855c3))

# [0.76.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.75.0...0.76.0) (2026-11-13)


### Bug Fixes

* **catalog:** project Pyroscope into the homelab services catalog ([914b9f8](https://github.com/AlbanAndrieu/nabla-compose/commit/914b9f8e106f1f00d1740eca2a89d54057a468da))
* **cloudflare:** name the Access apps after the fastapi-sample host ([19d428d](https://github.com/AlbanAndrieu/nabla-compose/commit/19d428d7997a3651e6c7b3e568f9eef21b01f12e))
* **mcp:** start the Sentry MCP server when SENTRY_URL is exported ([997e0c9](https://github.com/AlbanAndrieu/nabla-compose/commit/997e0c982613985f80929519d5338fb5a603d750))
* **postgres-exporter:** read the rendered DSN without its quotes ([bda23dd](https://github.com/AlbanAndrieu/nabla-compose/commit/bda23ddb1c2f68af37d87577618081615cd80b77))
* **postgres:** refuse plaintext remote connections with hostssl ([9ed3ab7](https://github.com/AlbanAndrieu/nabla-compose/commit/9ed3ab74ad582b8d352252197ab38f15a80ff24b))
* **postgres:** silence SC2317 for report-invoked TLS checks ([869ba44](https://github.com/AlbanAndrieu/nabla-compose/commit/869ba4421cd510f63e39fb7e4fd7c4e5fa4dfd95))


### Features

* **clamav:** move ClamAV from the TrueNAS catalog to a Compose App ([6135f5f](https://github.com/AlbanAndrieu/nabla-compose/commit/6135f5f857896eb16071df820b299a3773bc37dc))
* **postgres-exporter:** activate the exporter App ([9707f1c](https://github.com/AlbanAndrieu/nabla-compose/commit/9707f1cfdf763f7f761c6296181256b3016c2b11))

# [0.75.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.74.0...0.75.0) (2026-11-13)


### Bug Fixes

* **catalog:** repoint wrong Sample probes and cover running TrueNAS services ([b692abb](https://github.com/AlbanAndrieu/nabla-compose/commit/b692abbf3308f8bc96b9516df7993e29f9e6eee5))
* **prometheus:** mark Keycloak, NetBox and Dependency-Track planned ([2693416](https://github.com/AlbanAndrieu/nabla-compose/commit/2693416d3a4378f1a2dc91d6e55f49d03d40e10e))


### Features

* **gatus:** monitor InfluxDB, MongoDB and the running planned Apps ([11b41e2](https://github.com/AlbanAndrieu/nabla-compose/commit/11b41e2e4102b3b809e02b93f6133c4219d502e3))

# [0.74.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.73.0...0.74.0) (2026-11-12)


### Bug Fixes

* **homarr:** stop crashing on boards Homarr v2.6 cannot list ([2108f06](https://github.com/AlbanAndrieu/nabla-compose/commit/2108f0657836873bb3feece51abd2451419c6a80))
* **postgres:** verify the server certificate from Plumber and Sample ([8a38c6f](https://github.com/AlbanAndrieu/nabla-compose/commit/8a38c6f20a30b22af73e64c00efa6b58a8c18ab9))
* **reboot:** reorder resume waves around display, CrowdSec and n8n ([64d9bb5](https://github.com/AlbanAndrieu/nabla-compose/commit/64d9bb5a6b4270c1f612093147b0f9a2acef0959))


### Features

* **homarr:** write code-managed boards in full with sections and status ([52aaf91](https://github.com/AlbanAndrieu/nabla-compose/commit/52aaf917f5f3f27ece97ed9de268cb15deebe4fc))

# [0.73.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.72.0...0.73.0) (2026-11-12)


### Features

* **secrets:** declare the runtime secrets missing from the Vaultwarden manifest ([170813f](https://github.com/AlbanAndrieu/nabla-compose/commit/170813f0afc854c2ccf0f20d0f922e37ee73306b))

# [0.72.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.71.0...0.72.0) (2026-11-12)


### Bug Fixes

* **homarr:** keep waiting when the API read times out ([9055166](https://github.com/AlbanAndrieu/nabla-compose/commit/9055166c7553bb253eb58c0aac961ff862c9bc22))
* **homarr:** send pingUrl, which Homarr v2.6 requires again ([8cb584a](https://github.com/AlbanAndrieu/nabla-compose/commit/8cb584ad929b0e36773858f9a4e9ba8563d09979))
* **reboot:** keep resuming later waves when Wazuh fails ([59188a2](https://github.com/AlbanAndrieu/nabla-compose/commit/59188a295305758552d489f383ee52c2578af80d))
* **reboot:** refuse to bundle a commit with an older materializer ([efa603e](https://github.com/AlbanAndrieu/nabla-compose/commit/efa603ec984ee19a18d9e742085f7e7668a225a5))
* **reboot:** start openclaw-gateway after the Docker socket proxy ([950984a](https://github.com/AlbanAndrieu/nabla-compose/commit/950984a7f0db1c3e64ed79224faf85aa3aaa72f7))
* **secrets:** let the Grafana item exist without an admin password ([b3e413b](https://github.com/AlbanAndrieu/nabla-compose/commit/b3e413b18e4232200713f7543519cd80c5b22be2))


### Features

* **github:** import 16 more repositories to enforce delete_branch_on_merge ([83648c8](https://github.com/AlbanAndrieu/nabla-compose/commit/83648c85a7307518b3a4579dfb82ffe8976031c0))
* **postgres:** enable TLS 1.3 with a small local CA ([1d4900f](https://github.com/AlbanAndrieu/nabla-compose/commit/1d4900f4098167c01bbbf86f19942123746e3eb0))

# [0.71.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.70.0...0.71.0) (2026-11-12)


### Bug Fixes

* **garage:** route the public hostname to the WebUI, keep the Admin API LAN-only ([709aa79](https://github.com/AlbanAndrieu/nabla-compose/commit/709aa79b01b4dbd02943cc2f5e3ab0c3beb9b4ab))
* **secrets:** read canonical runtime files and give postgres-exporter its own App ([1673f32](https://github.com/AlbanAndrieu/nabla-compose/commit/1673f329bd19d682ad9af04060274e36562bd354))


### Features

* **github:** import nabla-servers-bower-sample to enforce delete_branch_on_merge ([b1e3084](https://github.com/AlbanAndrieu/nabla-compose/commit/b1e30849fc2b1719bd505cdce8f2bc4dbcca02ac))

# [0.70.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.69.1...0.70.0) (2026-11-12)


### Bug Fixes

* **catalog:** declare the newly active Apps in the operator inventories ([366dcb4](https://github.com/AlbanAndrieu/nabla-compose/commit/366dcb46d00355e213c42779892b9fd33c35ec9d))
* **reboot:** start cloudflared and Vaultwarden before the data waves ([2dd4bd7](https://github.com/AlbanAndrieu/nabla-compose/commit/2dd4bd7420a4cac5e0fc15582859e7d070225c42))


### Features

* **catalog:** mark akvorado, crowdsec, dsomm and n8n active ([bd5fadf](https://github.com/AlbanAndrieu/nabla-compose/commit/bd5fadfc9e919478e92134b4c333bdf30f011c69))
* **uptime-kuma:** add repository-owned Uptime Kuma Custom App ([5b506cf](https://github.com/AlbanAndrieu/nabla-compose/commit/5b506cf80ed53b9c5cdb4072bd8293d257f3fafd))

## [0.69.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.69.0...0.69.1) (2026-11-12)


### Bug Fixes

* **homarr:** wait up to 3 minutes for the API before syncing apps ([80221d1](https://github.com/AlbanAndrieu/nabla-compose/commit/80221d12cb88c134b4c4d93377071b979ca12ba0))
* **reboot:** map the 14 runtime-only Apps into the lifecycle topology ([6f96acb](https://github.com/AlbanAndrieu/nabla-compose/commit/6f96acbb303627cce48e843352ccb1a227bd62c1))
* **reboot:** run App gates after resume and ship them in the bundle ([4f9c00b](https://github.com/AlbanAndrieu/nabla-compose/commit/4f9c00b65ccf852c8f7dbab6f46d64cef5076d27))

# [0.69.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.68.0...0.69.0) (2026-11-12)


### Bug Fixes

* **joplin:** pin the published 3.7.3 server image by digest ([62747d8](https://github.com/AlbanAndrieu/nabla-compose/commit/62747d8c1ee0c3d07767b215fd8ebd0581a3fd50))
* **netbox,dependency-track:** reach the shared PostgreSQL and Redis ([9401633](https://github.com/AlbanAndrieu/nabla-compose/commit/940163386c9abadb0651b38e75081514b32a47f0))
* **ntopng:** set the admin password from Vaultwarden before the UI starts ([b3c21e6](https://github.com/AlbanAndrieu/nabla-compose/commit/b3c21e6c40122af68940612b1462a7527fa1e358))
* **observability,sample:** bound noisy Docker logs and wait longer for Sample ([1e87f0b](https://github.com/AlbanAndrieu/nabla-compose/commit/1e87f0b4ba8c368a85df4020fd5325943aeb74c5))
* **observability:** silence Loki deletion errors, unmonitor stopped apps ([cf1da09](https://github.com/AlbanAndrieu/nabla-compose/commit/cf1da0946e641ea8b5dfd3e2943c1fbe8bf975f5))
* **openwebui:** use a dedicated LiteLLM virtual key, not the master key ([e3f2c15](https://github.com/AlbanAndrieu/nabla-compose/commit/e3f2c15c1649d564974d87bdde01b5ec6fc108eb))
* **plumber:** reach the shared PostgreSQL and Redis with the Sample shortcut ([d3b9b79](https://github.com/AlbanAndrieu/nabla-compose/commit/d3b9b79fac52e028f0eb78327a0ed7ef43a86a95))
* **prometheus:** wake the dead Traefik, ClickHouse and cAdvisor alerts ([f693f59](https://github.com/AlbanAndrieu/nabla-compose/commit/f693f596d2d2c059dffc4e724fbbdcd205c82b40))
* **scanopy:** stop exposing a privileged, claimable discovery daemon ([74aad3d](https://github.com/AlbanAndrieu/nabla-compose/commit/74aad3d31fec85686ede1d8d9f279d90e59d8a4b))
* **truenas:** make the FastAPI cron post-check explain itself ([1194f2e](https://github.com/AlbanAndrieu/nabla-compose/commit/1194f2e3a598a4d5465dec80c2afe9855dfd648a))


### Features

* **alertmanager:** notify Slack through an incoming webhook ([59e76a5](https://github.com/AlbanAndrieu/nabla-compose/commit/59e76a5c5478efb687d315b19041d40f72049df1))
* **grafana,langfuse:** provision Grafana's LLM plugin, close Langfuse SSRF ([ad27c0d](https://github.com/AlbanAndrieu/nabla-compose/commit/ad27c0dbd502c754fcefe0d112f0691c88b54fe2))
* **homarr,litellm:** connect the Homarr assistant to LiteLLM as code ([d3e7fb5](https://github.com/AlbanAndrieu/nabla-compose/commit/d3e7fb5d25a4310b0222f5e204c631a47a451e00))
* **langfuse:** route Ask AI and LLM connections through LiteLLM ([04672ea](https://github.com/AlbanAndrieu/nabla-compose/commit/04672ea5777e785a72283fb6d03cc8d154ccd5b1))
* **ntopng:** run the free Community edition from a reviewed config file ([df7ff66](https://github.com/AlbanAndrieu/nabla-compose/commit/df7ff66f634970224cd31f48257ee96d9ae12afd))
* **prometheus:** scrape Garage metrics ([c6f9ef8](https://github.com/AlbanAndrieu/nabla-compose/commit/c6f9ef8f67fad31527c8d960e900c82aff9a3c6d))
* **talos:** replace flannel with Cilium so NetworkPolicy is enforced ([5754a1f](https://github.com/AlbanAndrieu/nabla-compose/commit/5754a1f1c0fe2cd6b42bcb4d1186a8ac03a144f3))
* **wazuh:** prepare the rotation of the indexer bootstrap passwords ([e51b39c](https://github.com/AlbanAndrieu/nabla-compose/commit/e51b39cbda1ff782b8d00b6e7a71cdf9a3bc85de))

# [0.68.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.67.0...0.68.0) (2026-11-11)


### Bug Fixes

* **litellm:** give the healthcheck a start period longer than the startup ([7a8b27d](https://github.com/AlbanAndrieu/nabla-compose/commit/7a8b27dfb84828a8c373cc396f73c9865aa3ee4f))
* **openclaw:** let the coder key plan pass before the key exists ([54cadd7](https://github.com/AlbanAndrieu/nabla-compose/commit/54cadd7dcc9a7b489732127cb86b2c96f339dfbe))


### Features

* **prometheus:** scrape LiteLLM /metrics with a key limited to that route ([3409b15](https://github.com/AlbanAndrieu/nabla-compose/commit/3409b1565056ee7720e71999a9317ca4c191892e))

# [0.67.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.66.1...0.67.0) (2026-11-10)


### Bug Fixes

* **kafka:** reap zombies in the exporter container too ([92cdf9d](https://github.com/AlbanAndrieu/nabla-compose/commit/92cdf9d9c1acc3b5d77e8ca7d1e4278f468a0dee))
* **monitoring:** pause local Grafana alert evaluation ([5bc64b9](https://github.com/AlbanAndrieu/nabla-compose/commit/5bc64b99db622774d1052e324cbd1c624c48029d))
* **sample:** connect with sslmode=prefer while PostgreSQL TLS is off ([b773cc5](https://github.com/AlbanAndrieu/nabla-compose/commit/b773cc56cf49fdd2d32da84f1aaffc18661c733d))
* **scanopy:** pin server and daemon to v0.19.5 by digest ([4441992](https://github.com/AlbanAndrieu/nabla-compose/commit/44419922781a442e2d996e381d49590721cccc98))
* **secrets:** fail closed instead of public default passwords ([9fa9b79](https://github.com/AlbanAndrieu/nabla-compose/commit/9fa9b798b4cc56826b5a0e95ac89aa16755963bb))
* **truenas:** count only repository-owned Apps in the readiness report ([f4e3b05](https://github.com/AlbanAndrieu/nabla-compose/commit/f4e3b05233ab652c0e84a34caa392e30dede1e72))


### Features

* **cloudflare:** bypass Access for the Keycloak nabla realm and Joplin ([30474d5](https://github.com/AlbanAndrieu/nabla-compose/commit/30474d50603dff60726fea0f4a32636b62c81ee9))
* **cloudflare:** keep Vaultwarden /admin behind the nabla Access policy ([9bae623](https://github.com/AlbanAndrieu/nabla-compose/commit/9bae6237a211a0de92bff155712dca18e43e339a))
* **secrets:** declare ten legacy-path services in the manifest ([363b1eb](https://github.com/AlbanAndrieu/nabla-compose/commit/363b1ebc409167f53722e5d135bfc1625a1251f3))

## [0.66.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.66.0...0.66.1) (2026-11-10)


### Bug Fixes

* **cloudflare:** stop publishing postgres.albandrieu.com ([ebeeb0c](https://github.com/AlbanAndrieu/nabla-compose/commit/ebeeb0c589679a3ec40b71dc1f229503d7222e82))

# [0.66.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.65.2...0.66.0) (2026-11-10)


### Bug Fixes

* **catalog:** map the postgresbackup icon explicitly ([b5018a2](https://github.com/AlbanAndrieu/nabla-compose/commit/b5018a23eb73cc681486288fa2e87fb070c6bb73))
* **cloudflare:** encrypt the token unit state and plans client-side ([3753f1d](https://github.com/AlbanAndrieu/nabla-compose/commit/3753f1db79d3db6d819ac49c59f48513f8bd87b3))
* **cloudflare:** resolve token permission groups per scope ([7f65854](https://github.com/AlbanAndrieu/nabla-compose/commit/7f658549285cf6ca7f1d81bf7532b85bfd92ae0b))


### Features

* **cloudflare:** manage the OpenTofu apply token as code ([bcb9112](https://github.com/AlbanAndrieu/nabla-compose/commit/bcb911292e8b3a02108b9d54b0f32e9cb9454d9c))
* **sample:** connect FastAPI Sample to its dedicated fastapisample database over verified TLS ([fd98421](https://github.com/AlbanAndrieu/nabla-compose/commit/fd98421b814176c0ee586cc1e6cd286f220c8e63))

## [0.65.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.65.1...0.65.2) (2026-11-10)


### Bug Fixes

* **secrets:** read runtime dotenv values like Compose and stop needless quoting ([1514afa](https://github.com/AlbanAndrieu/nabla-compose/commit/1514afa66fadf784cad0a31d2f461aefac99c9b7))

## [0.65.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.65.0...0.65.1) (2026-11-10)


### Bug Fixes

* **cloudflare:** put the public PostgreSQL TCP route behind Access ([9d97520](https://github.com/AlbanAndrieu/nabla-compose/commit/9d975206033a406ffd24c9dfe8b311f619e18fd7))

# [0.65.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.64.1...0.65.0) (2026-11-10)


### Bug Fixes

* **ci:** address CodeQL and Biome findings on the media PR ([e77847a](https://github.com/AlbanAndrieu/nabla-compose/commit/e77847abf7b375dbb3d927b9866c97f857f07daa))


### Features

* **backup:** monthly/yearly Sentry archives and fastapisample database ([d250dae](https://github.com/AlbanAndrieu/nabla-compose/commit/d250daea1ecf6ade9bbbb7e75946f744457c9218))

## [0.64.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.64.0...0.64.1) (2026-11-10)


### Bug Fixes

* **mise:** relock Python on the 3.14.9 pin from mise.toml ([7e3efa1](https://github.com/AlbanAndrieu/nabla-compose/commit/7e3efa104834d1e848d6ee56fd613a5db683525b))
* **truenas:** stop homarr-sync crashing on a revoked key, give OpenRAG time to start, fix the volume plan exit code ([da2f76c](https://github.com/AlbanAndrieu/nabla-compose/commit/da2f76c26d314cde3765b3526b51d9a10c8409f8))

# [0.64.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.63.0...0.64.0) (2026-11-10)


### Bug Fixes

* **zfs,secrets:** light snapshot class for Nexus, Homarr vault import names ([36540b1](https://github.com/AlbanAndrieu/nabla-compose/commit/36540b1835dd1d0a76c06b96ec0ece15bbc3eb49)), closes [#335](https://github.com/AlbanAndrieu/nabla-compose/issues/335)
* **zfs:** rare snapshots for re-creatable data (Nexus monthly+yearly, bitcoind monthly) ([44ada56](https://github.com/AlbanAndrieu/nabla-compose/commit/44ada56fd6d2662fa87c91267265e6492bb6a4f8))


### Features

* **homeassistant:** migrate to Compose custom app and add read-only diagnostics ([a6f589f](https://github.com/AlbanAndrieu/nabla-compose/commit/a6f589f3b29eeeb33470adccd31ea15df27df816))

# [0.63.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.62.0...0.63.0) (2026-11-10)


### Bug Fixes

* **tests:** let the mocked dig answer for fastapi-sample.albandrieu.com ([9d803b0](https://github.com/AlbanAndrieu/nabla-compose/commit/9d803b0bd41530d859cfee571a04f8d9d0186e5c))


### Features

* **openclaw:** provision a scoped LiteLLM key for the coder agent ([10b3cca](https://github.com/AlbanAndrieu/nabla-compose/commit/10b3cca11ed13e2ad6f72f11b943ea477c1926b4))
* **openclaw:** ship the coder key at 10 EUR per week without restarts ([58db190](https://github.com/AlbanAndrieu/nabla-compose/commit/58db1909e218e10bbd9a396d778073ecf8735028))

# [0.62.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.61.0...0.62.0) (2026-11-10)


### Features

* **homelab:** publish Joplin via the tunnel, remove Elasticsearch/Kibana, fix Homarr sync, Keycloak on Talos, observability verifier ([7ad0173](https://github.com/AlbanAndrieu/nabla-compose/commit/7ad0173d165210f6608db1257d6c7c8e6c58948d))

# [0.61.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.60.2...0.61.0) (2026-11-10)


### Bug Fixes

* **catalog:** declare fastapi-sample.albandrieu.com as the FastAPI Sample staging hostname ([f3e9a2d](https://github.com/AlbanAndrieu/nabla-compose/commit/f3e9a2d681b1449f28c4b8648afef7f0f28ba9c9)), closes [#333](https://github.com/AlbanAndrieu/nabla-compose/issues/333)


### Features

* **homelab:** HA on bridge network, Keycloak as active Custom App, Databasus backup role ([14d12e2](https://github.com/AlbanAndrieu/nabla-compose/commit/14d12e240abb5b42d22568de01e564278f93a726))
* **keycloak:** nabla realm as code, master realm refused at the edge; HA and observability follow-ups ([b23e92e](https://github.com/AlbanAndrieu/nabla-compose/commit/b23e92e3366fea081629d7744f6502f7bcf43564)), closes [#380](https://github.com/AlbanAndrieu/nabla-compose/issues/380)
* **observability:** Prometheus jobs for Dependency-Track and NetBox, staged pg_dump databases, startup order for pending Apps ([d8ae22b](https://github.com/AlbanAndrieu/nabla-compose/commit/d8ae22b26ebf14bf1ebe5e38c7fc8f04366a5baa))
* **postgres-backup:** versioned pg_dump job replacing UI-only Databasus as the backup reference ([8bdadf4](https://github.com/AlbanAndrieu/nabla-compose/commit/8bdadf44f4cf2a3ba170dbe9be43cc46084da205))
* **secrets:** add value-blind Vaultwarden migration coverage and runtime parity receipt [skip ci] ([243b64a](https://github.com/AlbanAndrieu/nabla-compose/commit/243b64ad5c1d972fe0ab03f05705f5f9e7bbda4a))

## [0.60.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.60.1...0.60.2) (2026-11-10)


### Bug Fixes

* **compose:** retain existing DB endpoints with SAN verified TLS [skip ci] ([b0d73ab](https://github.com/AlbanAndrieu/nabla-compose/commit/b0d73ab1c29a57b9d89e7d978c8c1b88fd93098f))
* **compose:** retain existing DB endpoints with SAN verified TLS [skip ci] ([e639e65](https://github.com/AlbanAndrieu/nabla-compose/commit/e639e655033650319c65a21ccaaa3f5ef39b3d19))
* **security:** enforce verified PostgreSQL TLS for unused services [skip ci] ([17aa84a](https://github.com/AlbanAndrieu/nabla-compose/commit/17aa84a1f48eb125df14dcc4ae5a0ff706dfd3af))
* **security:** enforce verified PostgreSQL TLS for unused services [skip ci] ([e20b9fb](https://github.com/AlbanAndrieu/nabla-compose/commit/e20b9fbf40f1fc09f056fb03a3729932399be823))

## [0.60.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.60.0...0.60.1) (2026-11-09)


### Bug Fixes

* **truenas:** replay PR [#332](https://github.com/AlbanAndrieu/nabla-compose/issues/332) on current master and reconcile documentation ([8db35d3](https://github.com/AlbanAndrieu/nabla-compose/commit/8db35d355dd90e8b735007a94cb7e07a436647e2))

# [0.60.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.59.1...0.60.0) (2026-11-09)


### Bug Fixes

* **ci:** allow non-root promtool to read synthetic bearer-token fixtures ([5abc2bc](https://github.com/AlbanAndrieu/nabla-compose/commit/5abc2bc15512ba6635d73098290bd76bfc1d3957))
* **media:** reconcile Backstage, CycloneDX, Homarr and secret manifests ([e5e6c60](https://github.com/AlbanAndrieu/nabla-compose/commit/e5e6c60304254618efb01c40b9697e3624cfaf69))
* **media:** reconcile roadmap, Cloudflare, documentation and runtime contracts ([7bdc606](https://github.com/AlbanAndrieu/nabla-compose/commit/7bdc606302f9877c3fb00b7530170e94800278ad))
* **media:** restore canonical tuple ordering for topology relations ([d5f64a8](https://github.com/AlbanAndrieu/nabla-compose/commit/d5f64a833a1afc69acac7eb038734de02d18751e))
* **media:** structurally reconcile service catalogs and topology against master ([937dbb7](https://github.com/AlbanAndrieu/nabla-compose/commit/937dbb7203716cd28f1c05aefc4c6f4ad786b331))
* **media:** synchronize canonical catalog revision after rebase ([b4a7117](https://github.com/AlbanAndrieu/nabla-compose/commit/b4a7117e565119bb099889f2682904a51ad922f4))


### Features

* **iac:** manage tunnel DNS records and the media dataset profile as code ([e3a7373](https://github.com/AlbanAndrieu/nabla-compose/commit/e3a7373b22a3f92a9f06402336871771ff09c5f2))
* **media:** add telemetry and application configuration as code ([a0e1722](https://github.com/AlbanAndrieu/nabla-compose/commit/a0e1722d2459f5933538d6d4644b074aa311ce89))
* **truenas:** production-readiness matrix and per-App operations dispatcher ([8405845](https://github.com/AlbanAndrieu/nabla-compose/commit/8405845970834ba67b894ab0a97c67262125912d))

## [0.59.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.59.0...0.59.1) (2026-11-08)


### Bug Fixes

* **backups:** fail closed when every staged database is absent; preserve prior backups ([1674fec](https://github.com/AlbanAndrieu/nabla-compose/commit/1674fec6712d71d9a3d876b23ad24955123c22cb))
* **backups:** retain old recovery points when any database backup fails ([3830f6a](https://github.com/AlbanAndrieu/nabla-compose/commit/3830f6aed670236d886b3d944f0a04458638069c))
* **catalog:** order topology relations by canonical source,target,type tuple ([0f0448f](https://github.com/AlbanAndrieu/nabla-compose/commit/0f0448f2d6e52dd8ce52c05430e4f7169d76facf))
* **quality:** preserve executable mode on pending Apps rollout command ([b63281c](https://github.com/AlbanAndrieu/nabla-compose/commit/b63281c01da92aa20377167646d659c30669918a))
* **rebase:** reconcile PR [#330](https://github.com/AlbanAndrieu/nabla-compose/issues/330) with master monitoring, scripts and catalog ([96248bb](https://github.com/AlbanAndrieu/nabla-compose/commit/96248bba87a44a2a726cbdbc1ac9be65906dc532))

# [0.59.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.58.0...0.59.0) (2026-11-08)


### Bug Fixes

* **catalog:** start cloudflared before vaultwarden on reboot resume ([e31785e](https://github.com/AlbanAndrieu/nabla-compose/commit/e31785ee29ffe2dd15b0632bd677659f4ad2171b))
* **ci:** use ephemeral non-secret fixture for promtool credential file ([b95803f](https://github.com/AlbanAndrieu/nabla-compose/commit/b95803f5d445f3e572c03bb77ebf2594e3d76f57))
* **monitoring:** stop alerting on services never deployed on TrueNAS ([e5a4c16](https://github.com/AlbanAndrieu/nabla-compose/commit/e5a4c165bd8bf9becb5f95af383e25d26cfc798c))
* **rebase:** reconcile removed catalog Apps, regenerated observability artifacts and current runbooks ([9af9987](https://github.com/AlbanAndrieu/nabla-compose/commit/9af9987cf96b60c70a25077b730bc83d8d7c96f4))
* **submodules:** fetch apps/fastapi-sample over HTTPS ([512aad4](https://github.com/AlbanAndrieu/nabla-compose/commit/512aad42c2e7e24918c41a783757f9f64dcf4ba9)), closes [#300](https://github.com/AlbanAndrieu/nabla-compose/issues/300)


### Features

* **compose:** cap memory of every JVM service ([77e3d7c](https://github.com/AlbanAndrieu/nabla-compose/commit/77e3d7c6f0fcc4b416bcb25fee15bd0c346ba74c))
* **ddns-updater:** move DDNS updater to a dedicated Custom App ([1e2d110](https://github.com/AlbanAndrieu/nabla-compose/commit/1e2d110fe4574c2b56ef6b47de4374a37a64f86e))
* **dockhand:** prepare migration from catalog App to Custom App ([ffdfeaf](https://github.com/AlbanAndrieu/nabla-compose/commit/ffdfeafa71b084e324ee49fbc6549afecb5942ff)), closes [hi#risk](https://github.com/hi/issues/risk)
* **doco-cd:** disable Doco-CD and document its intended role ([d692200](https://github.com/AlbanAndrieu/nabla-compose/commit/d6922003a7822fd54d9db32600f74e1755f69df5))
* **prometheus:** scrape full workstation host metrics as workstation_node ([d8fb205](https://github.com/AlbanAndrieu/nabla-compose/commit/d8fb205ec5d9ae19fce040f186dc11416a3d3168))
* **truenas:** manifest-driven Custom App recreation and capture ([2424604](https://github.com/AlbanAndrieu/nabla-compose/commit/24246047b2fadb68262df795c7ed5c9ebd53d5c1))
* **truenas:** reconcile repository Compose Apps as TrueNAS Custom Apps ([dc618b7](https://github.com/AlbanAndrieu/nabla-compose/commit/dc618b7b3d57776fd0455f8e0d6dd0bf3553c7f8))

# [0.58.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.57.1...0.58.0) (2026-11-06)


### Bug Fixes

* **catalog:** bind stopped TrueNAS apps by appId and record owner decisions ([24018bc](https://github.com/AlbanAndrieu/nabla-compose/commit/24018bcefa0d49f7a0cd10d89aa2882566880cb5))
* **cloudflare:** address CodeQL findings in the Service Auth tooling ([faa93d6](https://github.com/AlbanAndrieu/nabla-compose/commit/faa93d67bcaef1ce18c1709ab0dbd9801d82fb0b))
* **truenas:** align deploy-ntopng.sh with deployer contracts ([e4403db](https://github.com/AlbanAndrieu/nabla-compose/commit/e4403dba743748fe320083858deb4e8deb5482da))


### Features

* **cloudflare:** restrict Keycloak to production paths, unpublish LiteLLM, add Service Auth tooling ([8e1ea2b](https://github.com/AlbanAndrieu/nabla-compose/commit/8e1ea2b6df8f8f1a2e75646376b97d5e8f8fb7fc))
* **truenas:** add gated ntopng custom app preflight and deployment contract [skip ci] ([ea81bf1](https://github.com/AlbanAndrieu/nabla-compose/commit/ea81bf143a8b91de8086cc38d6fa2bd3c3f4f0a4))

## [0.57.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.57.0...0.57.1) (2026-11-05)


### Bug Fixes

* **catalog:** align exposure catalog and tunnel routes with probe evidence ([fd9f08b](https://github.com/AlbanAndrieu/nabla-compose/commit/fd9f08b8d25c751bca256ae7879945ff2553b82f))

# [0.57.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.56.0...0.57.0) (2026-11-05)


### Features

* **openclaw:** pin nabla-openclaw to the TrueNAS cutover [skip ci] ([1f05d34](https://github.com/AlbanAndrieu/nabla-compose/commit/1f05d34eaed77c199aff395dc04e1d6c681fc44b)), closes [#9](https://github.com/AlbanAndrieu/nabla-compose/issues/9)


### Performance Improvements

* **fastapi:** borner la capture des processus enfants pendant leur exécution [skip ci] ([fbb4f93](https://github.com/AlbanAndrieu/nabla-compose/commit/fbb4f93de9c25e38b657bde701d59f0628175287))
* **truenas:** ajouter mode quick sans inventaires Docker/ZFS lourds [skip ci] ([9a4e290](https://github.com/AlbanAndrieu/nabla-compose/commit/9a4e290a879aa45ff732af84ddaa14f9dd3ac4f7))

# [0.56.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.55.0...0.56.0) (2026-11-03)


### Bug Fixes

* **compose:** keep postgres and doco-cd off the LAN ([ec2c239](https://github.com/AlbanAndrieu/nabla-compose/commit/ec2c239110a24e59ce2aa1c9dac7b7ca82aeb2f1))
* **compose:** publish workstation-only ports on loopback ([63197d5](https://github.com/AlbanAndrieu/nabla-compose/commit/63197d5ecdaaab8ecfb3a34efc9757e593c6a394))


### Features

* **truenas:** version the ZFS snapshot policy per dataset class ([3e502ba](https://github.com/AlbanAndrieu/nabla-compose/commit/3e502ba16ba2504719af543eade7e930be08e09b))
* **truenas:** versioned bitcoind and docker-socket-proxy Custom Apps ([e51726d](https://github.com/AlbanAndrieu/nabla-compose/commit/e51726d315aebb846a1a4bffd292252e2e76769d))

# [0.55.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.54.2...0.55.0) (2026-11-03)


### Bug Fixes

* **diagnostics:** aligner le corps du runner individuel pour Python [skip ci] ([9fe8df9](https://github.com/AlbanAndrieu/nabla-compose/commit/9fe8df936fe2c1889088ade41101037c104ad69c))
* **observability:** ne jamais compter PASS si l'état du contrôle le contredit [skip ci] ([4ae157d](https://github.com/AlbanAndrieu/nabla-compose/commit/4ae157da63b98f8cd3af41908c16beb16e630b23))
* **observability:** traiter sans exception les verdicts non hashables [skip ci] ([65d9fcd](https://github.com/AlbanAndrieu/nabla-compose/commit/65d9fcd42ee7350d4ad846308938d5d35bd6f3e7))


### Features

* **cloudflare:** import-first OpenTofu for the shared tunnel, DNS and Access [skip ci] ([bcce89c](https://github.com/AlbanAndrieu/nabla-compose/commit/bcce89c77988dfb6eb010dc3fe74cc8aa6c28b42))
* **cloudflare:** rename FastAPI Sample public hostname to fastapi-sample.albandrieu.com [skip ci] ([8c49bf6](https://github.com/AlbanAndrieu/nabla-compose/commit/8c49bf678fd8312484b8431f0290f8fce4b3c1c6))


### Performance Improvements

* **diagnostics:** exécution parallèle limitée à 2 sondes, opt-in et ordre stable [skip ci] ([63411da](https://github.com/AlbanAndrieu/nabla-compose/commit/63411dab1eb4f5e32d89e03d0a62a0bf6de28461))
* **truenas:** collecter app.query une seule fois et réutiliser le PID containerd [skip ci] ([1a3405b](https://github.com/AlbanAndrieu/nabla-compose/commit/1a3405b7cdff40b37d02d2f34577f322ac54c63e))

## [0.54.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.54.1...0.54.2) (2026-11-03)


### Bug Fixes

* **test:** pin the redacted roadmap archive blob ([c800c56](https://github.com/AlbanAndrieu/nabla-compose/commit/c800c560e9890f1dcf4d72187e56e1bbbc44f16e))
* **truenas:** bound docker system df in the performance diagnostic ([21e4fdb](https://github.com/AlbanAndrieu/nabla-compose/commit/21e4fdb6d4adbd843fef752c6e0a9f530a3b474c))
* **truenas:** flag container anomalies in the performance diagnostic ([cc3f9ca](https://github.com/AlbanAndrieu/nabla-compose/commit/cc3f9ca6f1eef2aa0b95f2288da5c431f0669773))

## [0.54.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.54.0...0.54.1) (2026-11-01)


### Bug Fixes

* **gatus:** deny-only responses cannot force outage exit status [skip ci] ([a97ec0e](https://github.com/AlbanAndrieu/nabla-compose/commit/a97ec0ec5db17ded85d201f891b3c0c78367db4d))
* **gatus:** expliciter les réexportations publiques pour les tests Ruff [skip ci] ([8a01e9d](https://github.com/AlbanAndrieu/nabla-compose/commit/8a01e9d965632fd766a9c1ad80f28be3548227d5))
* **triage:** aggregate ambiguous Gatus/Prometheus phase failures as unverified [skip ci] ([cb1a4a5](https://github.com/AlbanAndrieu/nabla-compose/commit/cb1a4a59648c729af5c3ba6def231c2b10f8bf9c))
* **triage:** avoid false outage when Gatus DOWN is only authentication denied [skip ci] ([d4a8724](https://github.com/AlbanAndrieu/nabla-compose/commit/d4a8724785498e7ba8acb51ee668301faa69ff39))


### Performance Improvements

* **gatus:** calculer les identifiants dupliqués une seule fois [skip ci] ([c827fe6](https://github.com/AlbanAndrieu/nabla-compose/commit/c827fe6db5f096de46a0bbf694f461820260ed41))

# [0.54.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.53.0...0.54.0) (2026-11-01)


### Features

* **backup:** alert on stale workstation Restic, snapshot cpool/backup [skip ci] ([899ec52](https://github.com/AlbanAndrieu/nabla-compose/commit/899ec527e26a029c6cc53e0375e2df4d6bb297af))

# [0.53.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.52.1...0.53.0) (2026-11-01)


### Bug Fixes

* **catalog:** ignore catalog descriptors owned by app submodules ([7d65743](https://github.com/AlbanAndrieu/nabla-compose/commit/7d65743bbaa1f0b4644fd7577ea57abb16f27645))


### Features

* **openclaw:** mount nabla-openclaw as the apps/openclaw submodule ([fb5fada](https://github.com/AlbanAndrieu/nabla-compose/commit/fb5fada2f9b6cd4a8b1b05ca03e57b9aae54c0b9))

## [0.52.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.52.0...0.52.1) (2026-11-01)


### Bug Fixes

* **scripts:** keep secrets out of argv and harden operator helpers ([#312](https://github.com/AlbanAndrieu/nabla-compose/issues/312)) ([fd009a2](https://github.com/AlbanAndrieu/nabla-compose/commit/fd009a2c22e9f1f88d0e317018450fd56564e9bd))

# [0.52.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.51.0...0.52.0) (2026-11-01)


### Features

* **secrets:** révocation d'urgence et audit de rétention ZFS ([#307](https://github.com/AlbanAndrieu/nabla-compose/issues/307)) ([69997f8](https://github.com/AlbanAndrieu/nabla-compose/commit/69997f875cd99d5c987a91396d3e428c4e182c84))

# [0.51.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.50.0...0.51.0) (2026-10-31)


### Bug Fixes

* **langfuse:** load secrets from /mnt/cpool/secrets/runtime/langfuse [skip ci] ([#302](https://github.com/AlbanAndrieu/nabla-compose/issues/302)) ([4704d1b](https://github.com/AlbanAndrieu/nabla-compose/commit/4704d1ba47fd26566c916e9153ddcfaff8df3367))
* **openclaw:** diagnostics fail-closed et alignement Node déclaratif ([#295](https://github.com/AlbanAndrieu/nabla-compose/issues/295)) ([c50806f](https://github.com/AlbanAndrieu/nabla-compose/commit/c50806f27535fd08c4668d948495c95089532ce9))
* **openclaw:** opt-in sudo LiteLLM logs and npm wrappers on TrueNAS ([#305](https://github.com/AlbanAndrieu/nabla-compose/issues/305)) ([73a86ae](https://github.com/AlbanAndrieu/nabla-compose/commit/73a86ae77a018f75822197618d90f135a0818894))
* **submodule:** remove fastapi-sample ./run-git-submodule.sh ([#301](https://github.com/AlbanAndrieu/nabla-compose/issues/301)) ([4aae658](https://github.com/AlbanAndrieu/nabla-compose/commit/4aae6582aee013437f9b67a8c70f2993171033bf)), closes [#295](https://github.com/AlbanAndrieu/nabla-compose/issues/295)
* **truenas:** recreate the missing sample App instead of failing app.update [skip ci] ([#304](https://github.com/AlbanAndrieu/nabla-compose/issues/304)) ([9705415](https://github.com/AlbanAndrieu/nabla-compose/commit/9705415da75ffc363a586c98722d04871f675a13))


### Features

* **langfuse:** declare runtime secrets in the Vaultwarden manifest [skip ci] ([#303](https://github.com/AlbanAndrieu/nabla-compose/issues/303)) ([16eba72](https://github.com/AlbanAndrieu/nabla-compose/commit/16eba722d95293bccd9f7ff09d38de566153d035))
* **litellm:** relay gpt-4.1/mini from TrueNAS to the Workstation proxy ([#306](https://github.com/AlbanAndrieu/nabla-compose/issues/306)) ([e8e4ef9](https://github.com/AlbanAndrieu/nabla-compose/commit/e8e4ef9ba5f1de2b0e93ba584dcc8b689f439369))

# [0.50.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.49.0...0.50.0) (2026-10-30)


### Bug Fixes

* **actions:** local-first budget inventory hardening ([#269](https://github.com/AlbanAndrieu/nabla-compose/issues/269)) ([420697d](https://github.com/AlbanAndrieu/nabla-compose/commit/420697dd86a49be1b36cad49457d786b478b3693))
* **diagnostics:** distinguer authentification attendue et santé Garage/LiteLLM ([#281](https://github.com/AlbanAndrieu/nabla-compose/issues/281)) ([5578c6b](https://github.com/AlbanAndrieu/nabla-compose/commit/5578c6b0d95a6cfc21baec40980a4c3b12104f44))
* **homelab:** diagnostics ciblés et reprise sécurisée des migrations ([#274](https://github.com/AlbanAndrieu/nabla-compose/issues/274)) ([eef5344](https://github.com/AlbanAndrieu/nabla-compose/commit/eef534487819a58f98dd73c865310a29dfd3c41e))
* **openclaw:** gates runtime, preuves 429 et réconciliation digest/cron ([#292](https://github.com/AlbanAndrieu/nabla-compose/issues/292)) ([4dcb67d](https://github.com/AlbanAndrieu/nabla-compose/commit/4dcb67dc80f85beb7d4b4307a60b374e55ab7264))
* **pfsense:** console regression and read-only Wi-Fi/DNS path triage ([#279](https://github.com/AlbanAndrieu/nabla-compose/issues/279)) ([4217df8](https://github.com/AlbanAndrieu/nabla-compose/commit/4217df8324be42dcdd8f21f6fa15cab0d6707a13))
* **pfsense:** diagnose recurring Unbound OOM, pfBlockerNG and Akvorado ([#275](https://github.com/AlbanAndrieu/nabla-compose/issues/275)) ([3c4c150](https://github.com/AlbanAndrieu/nabla-compose/commit/3c4c150d00d49d977dd2373f810d6f1fa47d26e8))
* **truenas:** fail-closed core dependency preflight from Catalog v2 ([#267](https://github.com/AlbanAndrieu/nabla-compose/issues/267)) ([2627a87](https://github.com/AlbanAndrieu/nabla-compose/commit/2627a87001f5a298e81a03f39226164e405c643f))
* **workstation:** align OpenClaw diagnostics and local gates [skip ci] ([#293](https://github.com/AlbanAndrieu/nabla-compose/issues/293)) ([aed7a61](https://github.com/AlbanAndrieu/nabla-compose/commit/aed7a61d5ed330d2192a130d6c6ebd0c534afd54))


### Features

* **apisix:** diagnostics post-migration et tests rapides Node 22/npm 10 ([#280](https://github.com/AlbanAndrieu/nabla-compose/issues/280)) ([b96a7c3](https://github.com/AlbanAndrieu/nabla-compose/commit/b96a7c33ca965a5225082d39adba9bf3a35d9c15)), closes [hi#memory](https://github.com/hi/issues/memory)
* **catalog:** autorité unique des icônes de services [skip ci] ([#272](https://github.com/AlbanAndrieu/nabla-compose/issues/272)) ([e9a962d](https://github.com/AlbanAndrieu/nabla-compose/commit/e9a962d80e920374ea8d209b836aad1be3fba73d))
* **hermes:** complete Opus priority and secure cloud-key activation gates ([#270](https://github.com/AlbanAndrieu/nabla-compose/issues/270)) ([bff84e6](https://github.com/AlbanAndrieu/nabla-compose/commit/bff84e6756d81f6fa086e4def167a784a50774e1))
* **hermes:** offline sandbox image pinned to mise.lock with smoke test [skip ci] ([#296](https://github.com/AlbanAndrieu/nabla-compose/issues/296)) ([ea25acc](https://github.com/AlbanAndrieu/nabla-compose/commit/ea25acc156f0c15308d5e752011f2ce1d786ad6c))
* **hermes:** offline sandbox image pinned to mise.lock with smoke test [skip ci] ([#297](https://github.com/AlbanAndrieu/nabla-compose/issues/297)) ([c8c0aea](https://github.com/AlbanAndrieu/nabla-compose/commit/c8c0aea6a363ec8d67a65db9a6196fb3122e6f5b))
* **homelab:** normaliser openwebui, ports LAN et migration contrôlée [skip ci] ([#273](https://github.com/AlbanAndrieu/nabla-compose/issues/273)) ([c3d1649](https://github.com/AlbanAndrieu/nabla-compose/commit/c3d16493ac85e270b0eb8cee1877197a43b178d5))
* **pfsense:** LAN Unbound diagnostics and Code secret-fixture repair ([#285](https://github.com/AlbanAndrieu/nabla-compose/issues/285)) ([08a739f](https://github.com/AlbanAndrieu/nabla-compose/commit/08a739f65eec9fe25f7ef4af098a0f0e075471db)), closes [hi#resource](https://github.com/hi/issues/resource)
* **platform:** fast concurrent Talos and bulk TrueNAS App refresh (operator gated) ([#271](https://github.com/AlbanAndrieu/nabla-compose/issues/271)) ([9905e12](https://github.com/AlbanAndrieu/nabla-compose/commit/9905e12c47b5a49e80778cf3527d0aa7216b342e))
* **truenas:** diagnose host and Docker pressure after Netdata stop [skip ci] ([#288](https://github.com/AlbanAndrieu/nabla-compose/issues/288)) ([e20b7e6](https://github.com/AlbanAndrieu/nabla-compose/commit/e20b7e63c82cbc8a8f406400eead658c3f911a23))


### Performance Improvements

* **quality:** réduire le coût de la boucle agent [skip ci] ([#294](https://github.com/AlbanAndrieu/nabla-compose/issues/294)) ([d718a01](https://github.com/AlbanAndrieu/nabla-compose/commit/d718a018cc7cbebdc027355a68631de77c2117c2))

# [0.49.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.48.0...0.49.0) (2026-10-22)


### Features

* **truenas:** redémarrage contrôlé Catalog v2, Gatus non bloquant et Apps facultatives en dernier ([#266](https://github.com/AlbanAndrieu/nabla-compose/issues/266)) ([a1effb5](https://github.com/AlbanAndrieu/nabla-compose/commit/a1effb5709564ec4f2ac7f88d44363efb1454c10))

# [0.48.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.47.1...0.48.0) (2026-10-21)


### Features

* **catalog:** cut over consumers to Backstage v2 and runtime secrets ([#265](https://github.com/AlbanAndrieu/nabla-compose/issues/265)) ([92c80d3](https://github.com/AlbanAndrieu/nabla-compose/commit/92c80d33bf518811faa9b235b90e03ec3ba5a057))
* **security:** préparer sept migrations GitOps et accès ops privé ([#263](https://github.com/AlbanAndrieu/nabla-compose/issues/263)) ([a99d344](https://github.com/AlbanAndrieu/nabla-compose/commit/a99d3444a422e76f53a34f18119315fa9e78e06f)), closes [hi#priority](https://github.com/hi/issues/priority)

## [0.47.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.47.0...0.47.1) (2026-10-18)


### Bug Fixes

* **quality,defectdojo:** approve merged deletions and align LAN importer ([#259](https://github.com/AlbanAndrieu/nabla-compose/issues/259)) ([ea6c9ff](https://github.com/AlbanAndrieu/nabla-compose/commit/ea6c9fff9fdf245da1935efda83bcf0ba3855c7c))

# [0.47.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.46.1...0.47.0) (2026-10-17)


### Bug Fixes

* **defectdojo:** close private Traefik/DNS acceptance after PR [#257](https://github.com/AlbanAndrieu/nabla-compose/issues/257) ([#258](https://github.com/AlbanAndrieu/nabla-compose/issues/258)) ([8b96e83](https://github.com/AlbanAndrieu/nabla-compose/commit/8b96e83e1319503b1e47c02e6921567051c73b6c))


### Features

* Watchtower read-only POC and deployment-unit catalog preview ([#257](https://github.com/AlbanAndrieu/nabla-compose/issues/257)) ([6f7ebb3](https://github.com/AlbanAndrieu/nabla-compose/commit/6f7ebb3faf3929c4319c579891e47cf871df4c27)), closes [#255](https://github.com/AlbanAndrieu/nabla-compose/issues/255) [#256](https://github.com/AlbanAndrieu/nabla-compose/issues/256) [#253](https://github.com/AlbanAndrieu/nabla-compose/issues/253) [#254](https://github.com/AlbanAndrieu/nabla-compose/issues/254)

## [0.46.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.46.0...0.46.1) (2026-10-17)


### Bug Fixes

* **mise:** Update mise lock on mac ([9c24290](https://github.com/AlbanAndrieu/nabla-compose/commit/9c242900f55479d078c9833e877e56160db2e626))

# [0.46.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.45.0...0.46.0) (2026-10-17)


### Bug Fixes

* **agent:** fiabiliser le scope Compose et Git offline ([#251](https://github.com/AlbanAndrieu/nabla-compose/issues/251)) ([6d98d16](https://github.com/AlbanAndrieu/nabla-compose/commit/6d98d16afddbd273f5a49dc18ddcce0146ba5ae6))
* **agent:** lever le blocage offline et borner les diagnostics ([#250](https://github.com/AlbanAndrieu/nabla-compose/issues/250)) ([d4cb4fd](https://github.com/AlbanAndrieu/nabla-compose/commit/d4cb4fd2e8f2a63ae8d719e9bfd239d337ca50db))
* **gatus:** réparer l'accès au YAML généré et reprendre la stabilisation runtime ([#253](https://github.com/AlbanAndrieu/nabla-compose/issues/253)) ([42e0521](https://github.com/AlbanAndrieu/nabla-compose/commit/42e0521d9653b381c2670d30da634ff98c1cf899))
* **gatus:** sécuriser la reprise et la validation du script de recovery ([#255](https://github.com/AlbanAndrieu/nabla-compose/issues/255)) ([74faf84](https://github.com/AlbanAndrieu/nabla-compose/commit/74faf841809baab92df2eac07bac742cb471b30f))
* **pfsense:** restaurer le bit exécutable du diagnostic [skip ci] ([#252](https://github.com/AlbanAndrieu/nabla-compose/issues/252)) ([38552ce](https://github.com/AlbanAndrieu/nabla-compose/commit/38552ce6a77189414470142b7c25e50c0f55518e))
* rendre le PoC Dagger reproductible avant benchmark ([#247](https://github.com/AlbanAndrieu/nabla-compose/issues/247)) ([704a145](https://github.com/AlbanAndrieu/nabla-compose/commit/704a145eb24d6544c7b83dbb054939454ba68e9b))
* **runtime:** finaliser Sentry, DSOMM et l’outillage TrueNAS ([#243](https://github.com/AlbanAndrieu/nabla-compose/issues/243)) ([d6a8238](https://github.com/AlbanAndrieu/nabla-compose/commit/d6a8238abf3b5bee7ccf3ca5188617e936e198d2))
* stabiliser DSOMM, Sentry et les migrations runtime TrueNAS ([#240](https://github.com/AlbanAndrieu/nabla-compose/issues/240)) ([1ffe637](https://github.com/AlbanAndrieu/nabla-compose/commit/1ffe637a7dae81ec11773f0b7bfeac05598e415d))
* **truenas:** diagnostiquer les Apps bloquées après reboot ([#239](https://github.com/AlbanAndrieu/nabla-compose/issues/239)) ([ca6792e](https://github.com/AlbanAndrieu/nabla-compose/commit/ca6792ee8bf3ecb9f462a8b9b376807a5901a7b0))
* **truenas:** stabiliser DSOMM et compacter les deployers ([#249](https://github.com/AlbanAndrieu/nabla-compose/issues/249)) ([64e7088](https://github.com/AlbanAndrieu/nabla-compose/commit/64e7088c20a9105d6a875da887278da5a6ba5d19))


### Features

* intégrer Context7 en mode free-first ([#244](https://github.com/AlbanAndrieu/nabla-compose/issues/244)) ([f93fbfd](https://github.com/AlbanAndrieu/nabla-compose/commit/f93fbfde7fbaaee67d7f0d6c6690f43fc26cf2aa))
* **observability:** generate outside-in SOS contracts [skip ci] ([#245](https://github.com/AlbanAndrieu/nabla-compose/issues/245)) ([c7fe16f](https://github.com/AlbanAndrieu/nabla-compose/commit/c7fe16faba4f1cc0615da56c398533b48ffbfef5))
* **pfsense:** durcir le diagnostic OOM et l’identité exporter ([#248](https://github.com/AlbanAndrieu/nabla-compose/issues/248)) ([8b03204](https://github.com/AlbanAndrieu/nabla-compose/commit/8b032048a5a10ec97d3f98b065f1628f79afbae4))
* préparer le PoC Dagger local-first ([#246](https://github.com/AlbanAndrieu/nabla-compose/issues/246)) ([74eadd2](https://github.com/AlbanAndrieu/nabla-compose/commit/74eadd295ca5663becda4430c33c75c8482f2eb7))
* **security:** préremplir DSOMM, déclarer OpenCRE et publier l’audit ([#238](https://github.com/AlbanAndrieu/nabla-compose/issues/238)) ([5e9516e](https://github.com/AlbanAndrieu/nabla-compose/commit/5e9516e54686e06c8f149c81689cbf0dbc14c80d))

# [0.45.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.44.0...0.45.0) (2026-10-03)


### Bug Fixes

* **pfsense:** harden automatic egress discovery ([9218e75](https://github.com/AlbanAndrieu/nabla-compose/commit/9218e75d2ee1b7fc817e5a0296ff55ae0707bca5))


### Features

* **pfsense:** auto-discover FastAPI Cloud egress sources ([477abcb](https://github.com/AlbanAndrieu/nabla-compose/commit/477abcb8f0b6fb149a9dd439984d799ba455af5b))

# [0.44.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.43.0...0.44.0) (2026-10-03)


### Features

* **security:** intégrer security-audit, cadrer DSOMM et planifier OpenCRE ([#233](https://github.com/AlbanAndrieu/nabla-compose/issues/233)) ([8b166d8](https://github.com/AlbanAndrieu/nabla-compose/commit/8b166d8f476f099d2be609ba9ee907e8dbef43ac))

# [0.43.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.42.0...0.43.0) (2026-09-28)


### Bug Fixes

* **health:** observer le runtime Talos via TrueNAS ([#225](https://github.com/AlbanAndrieu/nabla-compose/issues/225)) ([c6e8256](https://github.com/AlbanAndrieu/nabla-compose/commit/c6e825677783fe2fe3f9368b0a5f8366354e3951))


### Features

* **catalog:** complete priority Backstage materialization ([#218](https://github.com/AlbanAndrieu/nabla-compose/issues/218)) ([75ed3ea](https://github.com/AlbanAndrieu/nabla-compose/commit/75ed3ea9aea27181239b6250d4d82762bb142b76))
* **migration:** coupler P0.3 secrets, Backstage et OpenCode ([#224](https://github.com/AlbanAndrieu/nabla-compose/issues/224)) ([cf17647](https://github.com/AlbanAndrieu/nabla-compose/commit/cf1764738c52bfd1da14e53553c0ecab67ade413))
* **ops:** local-first control-plane and catalog follow-up [skip ci] ([#226](https://github.com/AlbanAndrieu/nabla-compose/issues/226)) ([983fe55](https://github.com/AlbanAndrieu/nabla-compose/commit/983fe55bebd7382efd01248ea7fa3c6782cfe535))

# [0.42.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.41.0...0.42.0) (2026-09-23)


### Bug Fixes

* **qg:** reconcile local contract drift and bound failure output ([#212](https://github.com/AlbanAndrieu/nabla-compose/issues/212)) ([d63acc5](https://github.com/AlbanAndrieu/nabla-compose/commit/d63acc5858dfa2cc0defc1f4c0c376a68626162e))


### Features

* **catalog:** continue v2 BIA and parity hardening ([#216](https://github.com/AlbanAndrieu/nabla-compose/issues/216)) ([6845cb4](https://github.com/AlbanAndrieu/nabla-compose/commit/6845cb4a740347d1812e4e8d33b37876ae5b6ca9))
* **catalog:** continue v2 medium-wave materialization ([#217](https://github.com/AlbanAndrieu/nabla-compose/issues/217)) ([7df2ae8](https://github.com/AlbanAndrieu/nabla-compose/commit/7df2ae807bf792faaed6f4f92fe503ca7eb304df))
* **catalog:** prepare Backstage v2 parity pilot ([#215](https://github.com/AlbanAndrieu/nabla-compose/issues/215)) ([2e7a718](https://github.com/AlbanAndrieu/nabla-compose/commit/2e7a718d6b8eca57b180bc5f6f8956472bcee02f))
* **secrets:** enforce Vaultwarden first-wave runtime acceptance ([#213](https://github.com/AlbanAndrieu/nabla-compose/issues/213)) ([61432ec](https://github.com/AlbanAndrieu/nabla-compose/commit/61432ecb8529542a7341702e28cf3ae9a9b14435))
* **secrets:** rebase initialization control plane on 0.41.0 [skip ci] ([#210](https://github.com/AlbanAndrieu/nabla-compose/issues/210)) ([49ee00f](https://github.com/AlbanAndrieu/nabla-compose/commit/49ee00f20aa0ae60ff60803d8b8b093a0532800f))

# [0.41.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.40.0...0.41.0) (2026-09-19)


### Features

* **runtime:** harden reboot lifecycle and P0.3 secret normalization ([#209](https://github.com/AlbanAndrieu/nabla-compose/issues/209)) ([f98c815](https://github.com/AlbanAndrieu/nabla-compose/commit/f98c815fcb7048639ebef273c81bc3a25a18113c))

# [0.40.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.39.0...0.40.0) (2026-09-19)


### Features

* **runtime:** bootstrap security tooling and harden reboot health ([#208](https://github.com/AlbanAndrieu/nabla-compose/issues/208)) ([74813a4](https://github.com/AlbanAndrieu/nabla-compose/commit/74813a4b5dd0b30130ade5db49bad72152d3d35e))

# [0.39.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.38.2...0.39.0) (2026-09-19)


### Features

* **security:** migrate Plumber and add security tooling Compose stacks ([#207](https://github.com/AlbanAndrieu/nabla-compose/issues/207)) ([533a382](https://github.com/AlbanAndrieu/nabla-compose/commit/533a382db1865f137aa065ecee231a25bbcdbb45))

## [0.38.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.38.1...0.38.2) (2026-09-13)


### Bug Fixes

* **traefik:** remove legacy Vaultwarden public int DNS owner ([#203](https://github.com/AlbanAndrieu/nabla-compose/issues/203)) ([2b74c30](https://github.com/AlbanAndrieu/nabla-compose/commit/2b74c30bb3f54d8a048757223e2f1d009dd8dc8f))

## [0.38.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.38.0...0.38.1) (2026-09-13)


### Bug Fixes

* **truenas:** surface lifecycle failures after app mutations ([#202](https://github.com/AlbanAndrieu/nabla-compose/issues/202)) ([5a9be57](https://github.com/AlbanAndrieu/nabla-compose/commit/5a9be576b23fae577fbb6d55078fef151449a84d))

# [0.38.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.37.0...0.38.0) (2026-09-13)


### Features

* **security:** add Cyberbro with MCP integration ([#199](https://github.com/AlbanAndrieu/nabla-compose/issues/199)) ([73aa3cc](https://github.com/AlbanAndrieu/nabla-compose/commit/73aa3cccb1868582631fb0429d62a2ef731479d6))

# [0.37.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.36.0...0.37.0) (2026-09-12)


### Bug Fixes

* **security:** close alert 19 and harden TrueNAS bootstrap ([#197](https://github.com/AlbanAndrieu/nabla-compose/issues/197)) ([47d47fb](https://github.com/AlbanAndrieu/nabla-compose/commit/47d47fbfffbbb42412b1b7a623f809b00c1911d5))


### Features

* **infra:** prepare GitHub governance with OpenTofu ([#198](https://github.com/AlbanAndrieu/nabla-compose/issues/198)) ([3c48ee9](https://github.com/AlbanAndrieu/nabla-compose/commit/3c48ee9d6298636becde7f00d478733d34753678))

# [0.36.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.35.0...0.36.0) (2026-09-12)


### Features

* **network:** add Scanopy topology discovery ([#196](https://github.com/AlbanAndrieu/nabla-compose/issues/196)) ([760e2bf](https://github.com/AlbanAndrieu/nabla-compose/commit/760e2bfb1087d86f30b14771fdb436de543111a6))

# [0.35.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.34.5...0.35.0) (2026-09-12)


### Features

* **homelab:** add Docling and Joplin services ([#195](https://github.com/AlbanAndrieu/nabla-compose/issues/195)) ([f3eceb8](https://github.com/AlbanAndrieu/nabla-compose/commit/f3eceb8e429eb51676a38a4695005b490d6d4d59))

## [0.34.5](https://github.com/AlbanAndrieu/nabla-compose/compare/0.34.4...0.34.5) (2026-09-12)


### Bug Fixes

* **observability:** reconcile topology and Prometheus targets ([#193](https://github.com/AlbanAndrieu/nabla-compose/issues/193)) ([bfe110b](https://github.com/AlbanAndrieu/nabla-compose/commit/bfe110b462d6dc4f8bc4d78b185255978e2d5655))

## [0.34.4](https://github.com/AlbanAndrieu/nabla-compose/compare/0.34.3...0.34.4) (2026-09-11)


### Bug Fixes

* **runtime:** stabilize Sentry Kafka and Suricata rule bootstrap ([#192](https://github.com/AlbanAndrieu/nabla-compose/issues/192)) ([6c147f1](https://github.com/AlbanAndrieu/nabla-compose/commit/6c147f19f49c9243860b1f2fd37be753e15edf5c))

## [0.34.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.34.2...0.34.3) (2026-09-11)


### Bug Fixes

* **truenas:** make reboot preparation resumable and diagnose CSI/runtime orphans ([#190](https://github.com/AlbanAndrieu/nabla-compose/issues/190)) ([7345685](https://github.com/AlbanAndrieu/nabla-compose/commit/73456852caf2ecac848ed836ef1aa3d13c1c60ba))

## [0.34.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.34.1...0.34.2) (2026-09-11)


### Bug Fixes

* **pfsense:** own recovery diagnostics in nabla-compose ([#188](https://github.com/AlbanAndrieu/nabla-compose/issues/188)) ([1bae89b](https://github.com/AlbanAndrieu/nabla-compose/commit/1bae89b9dac43aceda3eaaf0adf3003627a3229a))

## [0.34.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.34.0...0.34.1) (2026-09-11)


### Bug Fixes

* **csi:** restore TrueNAS publishContext attach path ([#187](https://github.com/AlbanAndrieu/nabla-compose/issues/187)) ([1e4fc2b](https://github.com/AlbanAndrieu/nabla-compose/commit/1e4fc2b54a0c5ddf144e196b5094276c2c3fc60d))

# [0.34.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.33.1...0.34.0) (2026-09-11)


### Features

* **kubernetes:** prepare Vault Falco and Kubara tooling ([#186](https://github.com/AlbanAndrieu/nabla-compose/issues/186)) ([e33f8b6](https://github.com/AlbanAndrieu/nabla-compose/commit/e33f8b64ea6677798faa5aa6d193107d6669302a))

## [0.33.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.33.0...0.33.1) (2026-09-11)


### Bug Fixes

* **ci:** enforce local-first gates and diagnose CSI provisioning ([#185](https://github.com/AlbanAndrieu/nabla-compose/issues/185)) ([d059e83](https://github.com/AlbanAndrieu/nabla-compose/commit/d059e83128813ce7d1ef1aeae2f0aef6199fc727))

# [0.33.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.32.3...0.33.0) (2026-09-10)


### Features

* **kubernetes:** harden Zero Trust posture and agent workflow ([#184](https://github.com/AlbanAndrieu/nabla-compose/issues/184)) ([3aa42f9](https://github.com/AlbanAndrieu/nabla-compose/commit/3aa42f95adbc25bfae2d387b01fb2541ef7bf3e0))

## [0.32.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.32.2...0.32.3) (2026-09-10)


### Bug Fixes

* **scrutiny:** harden final dual-host acceptance ([#183](https://github.com/AlbanAndrieu/nabla-compose/issues/183)) ([42e9fbe](https://github.com/AlbanAndrieu/nabla-compose/commit/42e9fbee9ca2fbadd9e4a64bdf933c0c26a7c409))

## [0.32.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.32.1...0.32.2) (2026-09-10)


### Bug Fixes

* **csi:** allow TrueNAS node plugin through Pod Security ([#182](https://github.com/AlbanAndrieu/nabla-compose/issues/182)) ([1d51223](https://github.com/AlbanAndrieu/nabla-compose/commit/1d5122388dc911a122a2567009a748ef210d42ea))

## [0.32.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.32.0...0.32.1) (2026-09-10)


### Bug Fixes

* **scrutiny:** restore workstation collector compose ownership ([#181](https://github.com/AlbanAndrieu/nabla-compose/issues/181)) ([fdcbdbd](https://github.com/AlbanAndrieu/nabla-compose/commit/fdcbdbd7e2e2a61e47c2f2a7cd9e10434bfa7762))

# [0.32.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.31.4...0.32.0) (2026-09-10)


### Features

* **catalog:** export canonical monitoring contract ([#179](https://github.com/AlbanAndrieu/nabla-compose/issues/179)) ([d2a1286](https://github.com/AlbanAndrieu/nabla-compose/commit/d2a1286400be507ee29bb1955abd5233a9464896))

## [0.31.4](https://github.com/AlbanAndrieu/nabla-compose/compare/0.31.3...0.31.4) (2026-09-10)


### Bug Fixes

* **scrutiny:** pin compatible workstation collector ([#177](https://github.com/AlbanAndrieu/nabla-compose/issues/177)) ([99b418e](https://github.com/AlbanAndrieu/nabla-compose/commit/99b418e4bf1bdaab3da0f3c8f1287407cba0eefb))

## [0.31.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.31.2...0.31.3) (2026-09-09)


### Bug Fixes

* **runtime:** harden TrueNAS operator CSI and Scrutiny acceptance ([#175](https://github.com/AlbanAndrieu/nabla-compose/issues/175)) ([c0cb371](https://github.com/AlbanAndrieu/nabla-compose/commit/c0cb371b8959fa27280d036b16c236e0092e7c20))

## [0.31.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.31.1...0.31.2) (2026-09-09)


### Bug Fixes

* **scrutiny:** allow InfluxDB migration buckets ([#176](https://github.com/AlbanAndrieu/nabla-compose/issues/176)) ([0c94fd5](https://github.com/AlbanAndrieu/nabla-compose/commit/0c94fd57e50753c0d67e862249a4a38cafae0a75))

## [0.31.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.31.0...0.31.1) (2026-09-09)


### Bug Fixes

* **runtime:** recover Sentry Wazuh and InfluxDB ([#173](https://github.com/AlbanAndrieu/nabla-compose/issues/173)) ([92676f7](https://github.com/AlbanAndrieu/nabla-compose/commit/92676f7b519a05d2b4b7856cefd3e8c1eaa81ccf))

# [0.31.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.30.0...0.31.0) (2026-09-09)


### Bug Fixes

* **catalog:** align PostgreSQL dependency identity ([#172](https://github.com/AlbanAndrieu/nabla-compose/issues/172)) ([b12d74f](https://github.com/AlbanAndrieu/nabla-compose/commit/b12d74fd9923626bad3281808dc64056d5d8dcfd))


### Features

* **truenas:** install persistent operator tools ([#174](https://github.com/AlbanAndrieu/nabla-compose/issues/174)) ([d994967](https://github.com/AlbanAndrieu/nabla-compose/commit/d99496773b209822ee5947bab63a4b6daa73d17a))

# [0.30.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.29.3...0.30.0) (2026-09-09)


### Bug Fixes

* **ops:** finish Scrutiny workstation and Wazuh lifecycle ([#170](https://github.com/AlbanAndrieu/nabla-compose/issues/170)) ([38cdae3](https://github.com/AlbanAndrieu/nabla-compose/commit/38cdae336017bc1c0784795ea9340e45ff0285b2))


### Features

* **kubernetes:** add TrueNAS NFS CSI for Talos ([#168](https://github.com/AlbanAndrieu/nabla-compose/issues/168)) ([f2ea655](https://github.com/AlbanAndrieu/nabla-compose/commit/f2ea655651480027d575292b8c938424bdcffdd4))

## [0.29.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.29.2...0.29.3) (2026-09-09)


### Performance Improvements

* **sample:** prefer immutable release image on TrueNAS ([#171](https://github.com/AlbanAndrieu/nabla-compose/issues/171)) ([faa037f](https://github.com/AlbanAndrieu/nabla-compose/commit/faa037f89c384c48c47ce32e2b3af06af1986988))

## [0.29.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.29.1...0.29.2) (2026-09-09)


### Bug Fixes

* **observer:** make catalog drift comparison actionable ([#169](https://github.com/AlbanAndrieu/nabla-compose/issues/169)) ([2ea87b1](https://github.com/AlbanAndrieu/nabla-compose/commit/2ea87b18a71b32968746dd67f596c4f6dcc67ee0))

## [0.29.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.29.0...0.29.1) (2026-09-09)


### Bug Fixes

* **scrutiny:** complete TrueNAS SMART-aware cutover ([#167](https://github.com/AlbanAndrieu/nabla-compose/issues/167)) ([acb0d34](https://github.com/AlbanAndrieu/nabla-compose/commit/acb0d34e1bc9713e99b0c706c5906fbf11b2b3a5))

# [0.29.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.28.0...0.29.0) (2026-09-08)


### Features

* **kubernetes:** resume Talos P0 after Sentry convergence ([#157](https://github.com/AlbanAndrieu/nabla-compose/issues/157)) ([14abb0e](https://github.com/AlbanAndrieu/nabla-compose/commit/14abb0ee667befd72fa81fda42b415dddcb8f12b))

# [0.28.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.27.2...0.28.0) (2026-09-08)


### Bug Fixes

* **ops:** align TrueNAS observer RBAC and Kubara ingress ([#153](https://github.com/AlbanAndrieu/nabla-compose/issues/153)) ([605a01d](https://github.com/AlbanAndrieu/nabla-compose/commit/605a01d5326497a224c4841e02ce4f6cf4a9e6e1))


### Features

* **diagnostics:** keep large checks compact in terminals ([#154](https://github.com/AlbanAndrieu/nabla-compose/issues/154)) ([7b9fa50](https://github.com/AlbanAndrieu/nabla-compose/commit/7b9fa5023004178babd645c9f2fe790382793bf7))

# [0.27.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.26.0...0.27.0) (2026-09-08)


### Features

* **ops:** harden TrueNAS observer and Kubernetes P0 gates ([#150](https://github.com/AlbanAndrieu/nabla-compose/issues/150)) ([3bd1ac4](https://github.com/AlbanAndrieu/nabla-compose/commit/3bd1ac46c1d2c1d2ff5d4100c2d449b3ea5cb15e))

# [0.26.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.25.3...0.26.0) (2026-09-08)


### Features

* **ops:** stabilize Talos Wazuh and Scrutiny gates ([#151](https://github.com/AlbanAndrieu/nabla-compose/issues/151)) ([d00e383](https://github.com/AlbanAndrieu/nabla-compose/commit/d00e383a319f3ac45f17db0b7f2f50a041a5a091))

## [0.25.3](https://github.com/AlbanAndrieu/nabla-compose/compare/0.25.2...0.25.3) (2026-09-08)


### Bug Fixes

* **talos:** recover VMs automatically after TrueNAS reboot ([#149](https://github.com/AlbanAndrieu/nabla-compose/issues/149)) ([0f6b15b](https://github.com/AlbanAndrieu/nabla-compose/commit/0f6b15b6b1345b0d860ca0b9eab07f86ff360cdc))

## [0.25.2](https://github.com/AlbanAndrieu/nabla-compose/compare/0.25.1...0.25.2) (2026-09-08)


### Bug Fixes

* **ci:** repair post-143 pre-commit gate ([#148](https://github.com/AlbanAndrieu/nabla-compose/issues/148)) ([7a1dfef](https://github.com/AlbanAndrieu/nabla-compose/commit/7a1dfefaad05234bc4081913601ef81d91a9e8a5))

## [0.25.1](https://github.com/AlbanAndrieu/nabla-compose/compare/0.25.0...0.25.1) (2026-09-08)


### Bug Fixes

* **truenas:** stabilize pfSense probes, Sentry and Wazuh ([#143](https://github.com/AlbanAndrieu/nabla-compose/issues/143)) ([48e91f0](https://github.com/AlbanAndrieu/nabla-compose/commit/48e91f0762f36897570017380de47ef19adc1bbd))

# [0.25.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.24.0...0.25.0) (2026-09-08)


### Features

* **talos:** start Kubernetes FastAPI acceptance gate ([#145](https://github.com/AlbanAndrieu/nabla-compose/issues/145)) ([754562a](https://github.com/AlbanAndrieu/nabla-compose/commit/754562a52b2c5c3d212551a96e3b4ca35b9a43d6))

# [0.24.0](https://github.com/AlbanAndrieu/nabla-compose/compare/0.23.6...0.24.0) (2026-09-08)


### Features

* **sentry:** diagnose TrueNAS DEPLOYING lifecycle ([#146](https://github.com/AlbanAndrieu/nabla-compose/issues/146)) ([af19e6e](https://github.com/AlbanAndrieu/nabla-compose/commit/af19e6e3fb59ab3f585164f3092ab6994560bbd5))

## [0.23.6](https://github.com/AlbanAndrieu/nabla-compose/compare/0.23.5...0.23.6) (2026-09-08)


### Bug Fixes

* **sample:** activate TrueNAS observer allowlist ([#144](https://github.com/AlbanAndrieu/nabla-compose/issues/144)) ([82e3402](https://github.com/AlbanAndrieu/nabla-compose/commit/82e3402374ca949ff7b4455219f410a6d7496afc))

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
