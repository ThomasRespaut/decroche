# Audit initial du projet Decroche

## 1) Vue d’ensemble de la structure

Le projet est une application Django orientée "agent vocal IA + téléphonie", structurée en apps:

- `accounts`: auth email/password custom + profil entreprise.
- `agents`: configuration agent IA (ton, voix, prompt, outils, features), base de connaissances, feedback.
- `calls`: journal des appels entrants/sortants côté métier.
- `twilio_bridge`: pont Twilio (UI de test appel, services de bridge, modèles d’appels sortants).
- `core`: pages principales (home/live demo), orchestration WebSocket/consumers côté UI.
- `decroche`: config projet (settings, urls, asgi/wsgi).

Cette séparation est saine pour un MVP produit: frontières fonctionnelles assez lisibles, avec un noyau infra (`decroche`) et des domaines métier par app.

## 2) Points forts observés

1. **Domaines bien séparés**: les apps correspondent à des bounded contexts clairs.
2. **Custom user model en place** (`accounts.User`) dès le départ: bon choix long terme.
3. **Présence de services applicatifs** (`agents/services/...`, `twilio_bridge/services.py`): évite de tout concentrer dans les vues.
4. **Préparation temps réel** via Channels/ASGI déjà branchée.
5. **Modèles orientés produit réel**: flags fonctionnels riches dans `AgentSettings` (RAG, booking, transfer, SMS, etc.).

## 3) Risques / dettes techniques prioritaires

### P0 — Cohérence de données / modèle

- **Duplication des données entreprise** entre `accounts.Profile` et `agents.BusinessProfile` (nom société, activité, adresse, horaires, notes...).
  - Risque: divergence de vérité, bugs de synchro, surcharge UI.
  - Recommandation: choisir une source de vérité (idéalement un seul modèle) + migration de consolidation.

- **Modèle `Call` peu relié au reste du domaine** (pas de FK explicite vers user/agent/session Twilio).
  - Risque: traçabilité limitée, analytics difficiles.
  - Recommandation: enrichir `Call` avec FKs (`user`, `agent_settings`) + identifiants de corrélation (`call_sid`, `session_id`).

### P0 — Environnement / prod readiness

- **`SECRET_KEY` par défaut faible** et `DEBUG=True` par défaut dans settings.
  - Risque: déploiement accidentel non sécurisé.
  - Recommandation: fail-fast en prod si env manquante (`DJANGO_SECRET_KEY` obligatoire; `DEBUG` défaut `False`).

- **Channel layer en mémoire** (`InMemoryChannelLayer`).
  - Risque: non viable en multi-worker / prod.
  - Recommandation: Redis channel layer configurable par env.

### P1 — Dépendances et reproductibilité

- **`requirements.txt` encodé en UTF-16 / non standard** (caractères nuls visibles).
  - Risque: installations cassées selon tooling CI/CD.
  - Recommandation: convertir en UTF-8 LF + verrouiller versions avec un workflow propre (`pip-tools`, `uv`, ou Poetry).

### P1 — Qualité / tests

- Beaucoup de fichiers `tests.py` existent, mais faible visibilité sur la profondeur des tests (unitaires/intégration/e2e).
  - Recommandation: stratégie par couches (models/services/views/websocket) + seuil minimal de couverture sur flux critiques (appel entrant, génération prompt, fallback).

## 4) Roadmap d’amélioration proposée

## Sprint A (stabilité & sécurité)

1. **Durcir la config**
   - `DEBUG=False` par défaut.
   - Validation startup des variables critiques.
   - Séparer settings `base/dev/prod`.

2. **Passer Channels sur Redis**
   - Ajouter `CHANNEL_LAYERS` piloté par `REDIS_URL`.
   - Prévoir fallback local en dev.

3. **Normaliser `requirements.txt`**
   - Conversion UTF-8.
   - Ajouter contrôle CI (`pip install -r requirements.txt` + check sécurité).

## Sprint B (modèle métier)

4. **Fusionner `Profile` / `BusinessProfile`**
   - Décider du modèle cible.
   - Ajouter migration de données + compat transitoire.

5. **Refactor Call Tracking**
   - Introduire un modèle `CallSession` (si absent/partiel) unifié pour inbound/outbound.
   - Lier Twilio SID, user, agent, timestamps, status normalisés.

6. **Event log d’appel**
   - Stocker événements (ringing, answered, transfer, hangup) pour audit/debug.

## Sprint C (produit IA)

7. **Pipeline RAG robuste**
   - Ingestion versionnée (chunking, metadata source, timestamps).
   - Stratégie fallback claire si RAG indisponible.

8. **Prompt engineering structuré**
   - Templates versionnés + tests snapshot sur `prompt_builder`.

9. **Observabilité IA**
   - Traces: latence, erreurs fournisseur, coût estimé, usage par outil.

## 5) Implémentations concrètes à rajouter rapidement (quick wins)

- **Tableau “Santé de l’agent”** dans le dashboard:
  - Twilio ready, dernière synchro, status inbound, voix, langue, outils actifs.

- **Audit trail administratif**:
  - Qui a changé quel setting d’agent, quand, et ancienne/nouvelle valeur.

- **Validation métier côté modèles/forms**:
  - Format E.164 pour téléphones.
  - Cohérence flags (`inbound_calls_enabled` interdit si `twilio_phone_number` vide).

- **Tests automatisés prioritaires**:
  - `AgentSettings.is_twilio_ready`
  - Construction prompt avec/sans profil business
  - Flux webhook Twilio principal

- **Gestion erreurs utilisateur**:
  - Messages UI homogènes et exploitables (français clair + codes internes de suivi).

## 6) Proposition d’architecture cible (à moyen terme)

- **Couche Domain Services explicite** (orchestration call flow, routing outils).
- **Couche Integration Providers** (Twilio/OpenAI) isolée derrière interfaces.
- **Task queue** (Celery/RQ) pour post-traitements asynchrones (résumés, SMS follow-up, indexation docs).
- **Monitoring centralisé** (Sentry + métriques applicatives).

## 7) Plan d’action recommandé (ordre)

1. Sécuriser settings + channels + dépendances.
2. Unifier le modèle de données entreprise et appels.
3. Renforcer tests critiques.
4. Ajouter observabilité et audit.
5. Itérer sur fonctionnalités produit (booking, transfer humain, RAG avancé).

---

Ce document sert de base de priorisation technique. L’étape suivante recommandée est de transformer ces points en tickets (P0/P1/P2) avec critères d’acceptation et estimation.
