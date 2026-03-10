# Audit de conformité réglementaire — RS-440

Pipeline Python qui lit un texte réglementaire, extrait les exigences,
les compare à une fiche produit, et produit un rapport classant chaque
exigence en **SATISFAIT / NON SATISFAIT / AMBIGU**.

---

## Lancement

```bash
python audit.py
```

Python 3.10+ requis. Aucune dépendance externe.

---

## Résultat attendu

```
══════════════════════════════════════════════════════════════
  RAPPORT D'AUDIT — AutoWeld Technologies SAS
══════════════════════════════════════════════════════════════
  Satisfait     :  4 / 11
  Non satisfait :  2 / 11
  Ambigu        :  5 / 11
──────────────────────────────────────────────────────────────

NON SATISFAIT :
  [REQ-06] La notice doit être disponible dans la langue de chaque pays...
    Raison   : Notice uniquement en français. Marchés : France, Italie, Portugal.
    Manquant : Traductions manquantes : italien, portugais.
  [REQ-08] Une évaluation des risques couvrant le cycle de vie complet...
    Raison   : Évaluation limitée à la phase d'utilisation uniquement.

AMBIGU (information présente mais insuffisante pour conclure) :
```

---

## Structure du projet

```
audit.py          Pipeline complet : parsing, structuration, comparaison, rapport
requirements.txt  Dépendances (aucune externe)
CHOIX.md          Méthode, décisions d'architecture, limites honnêtes
README.md         Ce fichier
```

---

## Architecture en quatre étapes

**Étape 1 — Parsing réglementaire**
Extraction des 11 exigences (REQ-01 à REQ-11) par regex avec lookahead.
Chaque exigence est un objet `Requirement` typé (id, texte, catégorie, conditionnalité).

**Étape 2 — Parsing fiche produit**
La fiche est transformée en dataclass `ProductSheet` (~20 champs typés).
Les synonymes sont résolus explicitement : "Bouton STOP d'urgence" → arrêt d'urgence,
"EN ISO 13850" → EN 13850, "schémas électriques" → circuits de commande.

**Étape 3 — Comparaison par règles**
Un évaluateur dédié par exigence, organisé en dispatch table.
Chaque évaluateur raisonne sur la **suffisance** de l'information, pas seulement
sa présence — c'est ce qui produit la catégorie AMBIGU sur les cas subtils.

**Étape 4 — Rapport**
Groupement par statut, raison explicite pour chaque cas,
champ `missing` sur les cas AMBIGU pour guider l'action corrective.

---

## Pourquoi un système à base de règles et pas du NLP ?

La conformité réglementaire est une question de **satisfaction logique**, pas de
similarité sémantique. Un modèle vectoriel (sentence-transformers) détecte que des
mots-clés se recoupent — il ne peut pas détecter que "mentionné en section 8.3
Entretien et nettoyage" n'est pas équivalent à "mentionné explicitement".

Le détail complet du raisonnement est dans `CHOIX.md`.
