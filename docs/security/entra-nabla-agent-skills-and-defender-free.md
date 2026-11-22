# H16 — Skills Azure recommandés (agent-first, least-privilege)

Catalogue vérifié le 22 novembre 2026 :
https://skills.sh/microsoft/azure-skills — dépôt officiel Microsoft
(63 skills, environ 19,6 M installations cumulées affichées).
Ne **pas** installer tout le pack par défaut : limiter les instructions
chargées par les agents et auditer les sources avant installation.

## Recommandés

- **Entra ID** :
  https://skills.sh/microsoft/azure-skills/entra-app-registration
  (~757 k installations affichées), inclut OAuth et app registrations ;
  utiliser pour auditer le bootstrap GitHub OIDC et Microsoft Graph.
- **Defender / audits Azure** :
  https://skills.sh/microsoft/azure-skills/azure-compliance
  (~757 k installations), inclut Azure Quick Review / Key Vault audits ;
  **ce skill n'est pas un connecteur Microsoft Defender** ni une licence.
- **RBAC en option** :
  https://skills.sh/microsoft/azure-skills/azure-rbac
  (~397 k installations) ; réserver aux futurs tests de délégation.

Installation manuelle sur la workstation dans un checkout de confiance :

```bash
npx skills add microsoft/azure-skills --skill entra-app-registration
npx skills add microsoft/azure-skills --skill azure-compliance
```

Examiner les SKILL.md et scripts installés avant de leur donner accès
à Azure CLI ou aux identités. Aucune installation distante exécutée par
ce commit.

## Microsoft Defender gratuit : plan de test

- **Foundational CSPM** de Defender for Cloud : **gratuit**,
  inventaire, Azure security recommendations et Secure Score.
  Depuis le 27 octobre 2026, les nouvelles souscriptions peuvent
  nécessiter un **opt-in** explicite au plan gratuit. Vérifier
  les réglages sur la souscription personnelle **avant activation**.
- **Defender CSPM avancé**, Defender for Servers/Containers/Endpoint
  et autres Defender ne sont **pas la même offre**. Defender for Cloud
  propose un essai initial de **30 jours** sur des plans éligibles ;
  les services peuvent devenir facturables ensuite. Certaines options
  (p. ex. Malware Scanning for Storage) sont facturables dès le départ.
- Pour le POC Entra, **aucun** `azurerm_security_center_subscription_pricing`
  n'est créé et **aucune protection payante** n'est activée par IaC.
  Prévoir ensuite un test read-only d'inventaire et des recommandations
  sur une souscription vide, avec budgets/alertes Azure si besoin.

Sources Microsoft :
- https://learn.microsoft.com/en-us/azure/defender-for-cloud/concept-cloud-security-posture-management
- https://learn.microsoft.com/en-us/azure/defender-for-cloud/free-trial
- https://azure.microsoft.com/en-us/pricing/details/defender-for-cloud/
- https://learn.microsoft.com/en-us/azure/defender-for-cloud/tutorial-enable-cspm-plan
