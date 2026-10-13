# Site Alban — submodules et déploiement Talos (préparation)

Le script TrueNAS existant `scripts/truenas/update-fastapi-sample.sh` déploie la plateforme FastAPI avec ses contrôles d'environnement et ne doit pas être remplacé par une simple mise à jour Git.

`scripts/truenas/update-application-submodules.sh --check` examine les SHAs épinglés des submodules `fastapi-sample` et `apps/nabla-site-alban`. `--update` effectue un fetch explicite des révisions `origin/master`, refuse les arborescences modifiées et laisse le commit des gitlinks à la revue humaine. Aucun push ni redéploiement TrueNAS n'est implicite. Cette commande a besoin de DNS GitHub et doit être exécutée sur un checkout autorisé.

`scripts/talos/deploy-site-alban.sh --render` génère une maquette de Namespace, Deployment, Service et Ingress. L'image `SITE_ALBAN_K8S_IMAGE` **doit être épinglée en `@sha256:<digest>`**. Le script n'est pas un builder d'image et ne doit pas déployer une image construite sans vérification du runtime Next.js non-root, des permissions de cache, de ses variables et de ses routes. Modes : `--preflight`, `--server-dry-run`, `--apply` (uniquement si `SITE_ALBAN_K8S_ALLOW_APPLY=true`).

Le hostname privé `alban-site.int.albandrieu.com` est un **candidat**, pas une entrée DNS confirmée. Conserver le domaine public Vercel inchangé. Valider Traefik/IngressClass, DNS local, TLS, absence de conflit Ingress, sécurité egress, probes et rollback avant toute activation. Pas de modification automatique de Cloudflare, Traefik ou pfSense.

Critères de réussite K8s : `kubectl apply --dry-run=server`, Pod Ready, HTTP `/fr` 200, TLS interne valide, métriques et logs consultables, rollback testé, zéro exposition publique additionnelle. Tout résultat non exécuté reste **NOT_RUN**.
