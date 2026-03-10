# CHOIX.md — Méthode, décisions de conception et limites

## Analyse préalable au code

Avant d'écrire la moindre ligne, les deux textes ont été lus en entier et les divergences
identifiées manuellement. C'est cette étape qui a déterminé toute l'architecture.

Résultat de l'analyse :

| REQ   | Verdict attendu  | Raison                                                                      |
|-------|------------------|-----------------------------------------------------------------------------|
| REQ-01 | AMBIGU          | Déclaration "EN COURS" — prévue mais non finalisée                         |
| REQ-02 | AMBIGU          | Signataire identifiée mais déclaration non signée, habilitation non confirmée |
| REQ-03 | AMBIGU          | Marquage CE sur le tableau de commande uniquement, pas sur la machine       |
| REQ-04 | SATISFAIT        | Schémas électriques présents ; absence hydraulique justifiée (tout-électrique) |
| REQ-05 | SATISFAIT        | Notice présente                                                             |
| REQ-06 | NON SATISFAIT    | Notice uniquement en français ; marchés : France + Italie + Portugal        |
| REQ-07 | AMBIGU          | Risques résiduels en section "Entretien et nettoyage" — couverture partielle suspectée |
| REQ-08 | NON SATISFAIT    | Évaluation limitée à la phase d'utilisation, cycle de vie complet non couvert |
| REQ-09 | SATISFAIT        | Enceinte de protection avec accès verrouillé                               |
| REQ-10 | SATISFAIT        | EN ISO 13850 = EN 13850 (même norme, nomenclature ISO actualisée)          |
| REQ-11 | AMBIGU          | Catégorie "standard" auto-déclarée sur la base d'une évaluation incomplète |

---

## Étape 1 — Structuration des exigences

### Format choisi : dataclass `Requirement`

Chaque exigence est un objet typé avec `id`, `text`, `category`, et deux champs
de conditionnalité (`conditional`, `condition`).

Ce choix n'est pas anodin. REQ-11 ne s'applique que si la machine est à risque élevé :
c'est une **exigence conditionnelle**. La modéliser explicitement dans la structure
plutôt que dans la logique de la fonction permet de séparer la donnée du raisonnement.

### Extraction par regex

```python
r"(REQ-\d+)\s*:\s*(.*?)(?=REQ-\d+\s*:|$)"
```

- `.*?` : quantificateur non-greedy — s'arrête dès que possible
- `(?=...)` : lookahead positif — vérifie ce qui suit sans le consommer

Collapse des espaces (`" ".join(text.split())`) pour normaliser les sauts de ligne.

---

## Étape 2 — Structuration de la fiche produit

### Format choisi : dataclass `ProductSheet`

La fiche est transformée en ~20 champs typés à sémantique précise. Ce choix repose
sur une distinction fondamentale :

- **Parsing syntaxique** : extraire "OUI" de la valeur d'un champ
- **Parsing sémantique** : modéliser ce que "OUI, apposé sur le tableau de commande"
  signifie dans le domaine réglementaire

Un parsing plat `clé → valeur` perd l'information contextuelle. Avec `ProductSheet`,
`ce_marking_present = True` et `ce_marking_location = "tableau de commande"` sont
deux faits distincts, tous deux nécessaires pour évaluer REQ-03.

### Points de vigilance traités

**Synonymes explicitement résolus**
- "Bouton STOP d'urgence" → `emergency_stop_present` (synonyme de "dispositif d'arrêt d'urgence")
- "Schémas électriques et pneumatiques" → circuits de commande (REQ-04)
- "EN ISO 13850" → même norme que "EN 13850" (normalisation via `_normalize_standard()`)

**Scope de l'évaluation des risques**
Regex sur "utilisation uniquement" vs "cycle de vie complet" pour distinguer
une évaluation partielle d'une évaluation complète.

**Langues de la notice**
Extraction depuis la ligne `notice_d'instructions` uniquement, pas les autres sections,
pour éviter de faux positifs.

**Localisation du marquage CE**
"tableau de commande" ≠ "machine" — distinction capturée dans `ce_marking_location`.

---

## Étape 3 — Comparaison et rapport

### Architecture : système à base de règles (Rule-Based System)

Un RBS est composé de trois éléments :
- **Base de faits** : le `ProductSheet` peuplé
- **Base de règles** : les fonctions `evaluate_reqXX`
- **Moteur d'inférence** : la boucle `evaluate_all`

Chaque règle suit le même schéma de priorité :
1. Tester d'abord le cas NON SATISFAIT clair
2. Tester le cas SATISFAIT net
3. Tous les cas intermédiaires → AMBIGU avec `missing` documenté

### Pourquoi pas la similarité sémantique (NLP vectoriel) ?

Une approche sentence-transformers calculerait la similarité cosinus entre le vecteur
de l'exigence et le vecteur du champ de la fiche.

Le problème fondamental : ces modèles capturent la **similarité distributionnelle**
(deux phrases proches si elles apparaissent dans des contextes similaires à l'entraînement).
La conformité réglementaire est une question de **satisfaction logique**, pas de similarité.

Exemple concret : "Risques résiduels : OUI, section 8.3 (Entretien et nettoyage)" et
"la notice doit mentionner explicitement les risques résiduels" ont une similarité cosinus
élevée. Un embedder retournerait SATISFAIT. La conclusion correcte est AMBIGU, parce que
*présent ≠ exhaustif* — et ce raisonnement pragmatique est hors de portée d'un vecteur.

La limite théorique : la similarité vectorielle opère au niveau **sémantique**
(sens des mots). La conformité réglementaire opère au niveau **pragmatique**
(implication dans le contexte d'usage). Ce sont deux niveaux distincts.

### Dispatch table

```python
EVALUATORS = {"REQ-01": evaluate_req01, ...}
result = EVALUATORS[req.id](req, product)
```

Lookup O(1) vs O(n) pour un if/elif. Surtout : ajouter REQ-12 ne modifie aucune
fonction existante. C'est le principe ouvert/fermé appliqué à la conformité.

---

## La vraie difficulté : la dépendance REQ-11 / REQ-08

C'est le cas le plus subtil du projet. REQ-11 est conditionnelle :
elle ne s'applique que si la machine est à risque élevé.

La fiche déclare la catégorie "standard" → réponse naïve : SATISFAIT.

Mais cette auto-déclaration repose sur une évaluation des risques incomplète (REQ-08
est NON SATISFAIT). La chaîne logique correcte est :

```
REQ-11 est satisfaite  SI  la machine est à risque standard
La machine est standard  SELON  l'évaluation des risques
L'évaluation des risques est NON CONFORME (REQ-08)
──────────────────────────────────────────────────────
DONC : on ne peut pas valider REQ-11 sur la base
       d'une donnée elle-même non conforme → AMBIGU
```

C'est une **dépendance de validité** : la conclusion d'une règle dépend de la validité
d'une prémisse évaluée par une autre règle. Valider REQ-11 sans voir cette dépendance
produirait un faux positif — le risque métier le plus grave dans un système de conformité
industrielle.

---

## Ce que "AMBIGU" signifie précisément

AMBIGU n'est pas "je ne suis pas sûr". C'est une conclusion précise :

> "Je peux prouver que l'information existe, mais je ne peux pas prouver
> qu'elle est suffisante pour satisfaire l'exigence."

Quatre distinctions que le projet illustre :

| Formulé dans la fiche | Requis par la norme | Verdict |
|---|---|---|
| Prévu avant livraison | Rédigé avant commercialisation | AMBIGU |
| Signataire identifiée | Représentant habilité confirmé | AMBIGU |
| Mentionné en section 8.3 | Mentionné explicitement | AMBIGU |
| Catégorie auto-déclarée | Catégorie vérifiable | AMBIGU |

En système critique (industrie, médical, aéronautique), ce principe s'appelle
**fail-safe** : en cas d'incertitude, adopter l'état le plus sûr. Ici, AMBIGU
renvoie à un humain plutôt que de laisser passer un faux SATISFAIT.

---

## Limites honnêtes

**Généralisation** : les évaluateurs sont spécifiques à ce document. Sur un nouveau
texte réglementaire, il faut réécrire les fonctions. Une version production utiliserait
un LLM pour extraire les règles d'évaluation depuis le texte normatif lui-même,
les règles structurées ne servant qu'à l'inférence finale.

**Dépendances inter-règles** : la dépendance REQ-11 / REQ-08 est gérée manuellement
dans `evaluate_req11`. Un graphe de dépendances explicite (DAG) serait plus robuste
à l'échelle.

**Tests unitaires** : chaque évaluateur est testable indépendamment avec des
`ProductSheet` mockés. Non implémenté faute de temps, mais l'architecture le permet
directement.

**Données d'entrée** : les textes sont embarqués pour la portabilité. Une fonction
`load_from_file(path)` suffit pour lire depuis des fichiers externes.

**Export** : rapport JSON ou CSV pour intégration dans un workflow de qualification
automatisé.
