# MORNING_BRIEFING.md — Briefing du matin (à la demande / job isolé)

> Modèle de rapport pour l'agent OpenClaw sur la Workstation.
> Ce fichier ne déclenche **aucune** exécution périodique à lui seul.
> Utiliser une tâche planifiée distincte du heartbeat natif, avec un budget
> et un nombre de tentatives explicitement limités.
> Ne jamais afficher de jetons, secrets, chemins privés, messages complets
> ni identifiants d'autres personnes dans le briefing.

## Règles de collecte

1. Récupérer les preuves disponibles depuis des sondes déjà autorisées.
2. Respecter le périmètre du réseau et des applications effectivement accessibles.
3. Signaler `Non vérifié` si une sonde, API ou autorisation manque.
4. Ne jamais présenter une synchronisation, un état de santé ou un email
   comme vérifié si aucune preuve horodatée ne le confirme.
5. Ne jamais ouvrir un coffre-fort, déclencher une réauthentification, explorer
   une conversation privée ou tenter une reconnexion sans autorisation dédiée.
6. Réutiliser les preuves Gatus/Prometheus/FastAPI plutôt que de solliciter
   les LLM pour chaque contrôle d'infrastructure.
7. Éviter les boucles de retry et les fallbacks vers un autre modèle payant.
8. Afficher un rapport bref en français, avec un horodatage Europe/Paris.
   Développer les détails uniquement sur demande.

## 📅 Briefing du matin — infrastructure personnelle

### 🌤️ Météo — Paris
- Conditions : `Non vérifié` sans source météo autorisée.
- Détail météo uniquement à la demande.

### 💽 État du système
- Disque : `<utilisé>` / `<total>`, libre `<libre>`, `<pourcentage>` %.
- RAM : `<utilisée>` / `<totale>`, libre `<libre>`.
- CPU : charge 1/5/15 minutes `<valeurs>` ; uptime `<durée>`.
- Services : LiteLLM, serveur web, PostgreSQL, OpenClaw Gateway.
- Pour chaque métrique, citer le collecteur et l'âge des données.

### 🚀 Sondes et incidents
- Gatus : nombre de sondes OK / DOWN / UNKNOWN selon la dernière collecte.
- Prometheus : targets UP / DOWN / UNKNOWN et erreurs de scrape.
- LiteLLM : liveliness, modèles exposés, métriques de quotas sans secrets.
- OpenClaw : erreurs récentes, cooldown, 429, état du Gateway.
- Mémoire : index `main` et `cron` signalés séparément, jamais reconstruits
  simplement pour produire le rapport.
- N'afficher que les anomalies nouvelles ou aggravées avec leur preuve.

### 📆 Calendriers
- Synchronisation CalDAV : `Vérifiée à <heure>` seulement avec une preuve
  d'exécution réussie ; sinon `Non vérifié`.
- Réunions : nombre et créneau des événements pertinents, sous réserve
  d'une intégration et d'un droit d'accès explicites.

### 📥 Messagerie
- Gmail : nombre d'éléments urgents / nécessitant une action, seulement si
  l'intégration authentifiée fonctionne.
- WhatsApp : résumer uniquement les échanges explicitement autorisés.
  Respecter la liste d'exclusion privée de l'utilisateur, sans jamais
  afficher les conversations exclues ni leurs métadonnées.
- Si un jeton est indisponible : afficher `Authentification requise`,
  sans tenter de contourner le coffre-fort ni divulguer l'identité du compte.

### ⚠️ Alertes et sécurité
- Incidents d'infrastructure : état / gravité / preuve horodatée.
- OpenClaw : avertissements de `doctor` et `health` uniquement si
  issus d'un diagnostic autorisé ; ne pas relancer de test payant.
- Distinguer panne réelle, sonde indisponible et diagnostic non exécuté.

### 📊 Tâches, issues et projets
- Tâches : `<nombre ou Non vérifié>`.
- En cours : `<nombre ou Non vérifié>`.
- Issues : `<nombre ou Non vérifié>`.
- Ne pas inférer ces comptes depuis des fichiers anciens.

## 🟢🟠🔴 Règles de présentation

- Disque et RAM : 🟢 <70 %, 🟠 70–85 %, 🔴 >85 %.
- CPU : 🟢 charge <3, 🟠 3–6, 🔴 >6.
- Donnée absente ou périmée : ⚪ UNKNOWN, jamais 🟢 par défaut.
- CPU : préciser que les seuils de charge ne sont pas normalisés au
  nombre de cœurs et restent des indicateurs simples.
- Éviter le HTML inline ; utiliser du Markdown lisible partout.

## Cadence et coût

- Ce document est destiné à une demande explicite ou à **un job isolé
  le matin** après configuration du scheduler natif de la version installée.
- La tâche planifiée doit avoir une seule exécution, un délai et un budget
  plafonnés. Ne pas l'exécuter dans le heartbeat `main` toutes les 30 min.
- Toute donnée manquante reste `Non vérifié` : aucun probe répété pour
  remplir à tout prix les champs du modèle.
