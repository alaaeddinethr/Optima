# Regulatory Compliance Audit: Machinery CE Requirements

Reads a regulatory text, extracts each requirement, checks it against a machine's product sheet and classifies it as **SATISFIED**, **NOT SATISFIED** or **AMBIGUOUS**, with the reason and, when something is missing, what would be needed to conclude.

[![CI](https://github.com/alaaeddinethr/Optima/actions/workflows/ci.yml/badge.svg)](https://github.com/alaaeddinethr/Optima/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

The case: an automated welding machine (AutoWeld Technologies) must meet 11 CE-marking requirements (declaration, marking, technical file, instructions, risk assessment, guards, emergency stop, notified body) before it can be sold in France, Italy and Portugal. The texts are in French, as in the original brief, so the report is too.

## Result

```
  RAPPORT D'AUDIT — AutoWeld Technologies SAS
  Satisfait     :  4 / 11
  Non satisfait :  2 / 11
  Ambigu        :  5 / 11
```

| | Requirements | Typical reasoning |
|---|---|---|
| Not satisfied | REQ-06, REQ-08 | Manual only in French while the machine is sold in Italy and Portugal; risk assessment covers use only, not the full life cycle |
| Ambiguous | REQ-01, 02, 03, 07, 11 | CE declaration "in progress" and unsigned; CE mark on the control panel only; residual risks listed under *Maintenance*; "standard" risk category self-declared on an incomplete assessment |
| Satisfied | REQ-04, 05, 09, 10 | "EN ISO 13850" recognised as the same standard as "EN 13850" |

The value is in the **ambiguous** class: a keyword search would mark "residual risks: yes, section 8.3" as compliant. The rule checks *where* they are documented and flags that a maintenance section probably does not cover all of them.

## Why rules and not NLP

Compliance is a question of logical sufficiency, not textual similarity. An embedding model sees that "CE declaration: in progress" is close to "a CE declaration must be drafted"; it cannot tell that "in progress" does not meet "before placing on the market". Each requirement therefore has its own evaluator in a dispatch table, reasoning on typed fields extracted from the product sheet. The full reasoning, the expected verdict for each requirement and the known limits are in [`CHOIX.md`](CHOIX.md) (French).

## Pipeline

1. **Requirements**: regex extraction into typed `Requirement` objects (id, text, category, conditional or not; REQ-11 only applies to high-risk machines).
2. **Product sheet**: parsed into a `ProductSheet` dataclass of about 20 fields, with explicit synonym resolution ("Bouton STOP d'urgence" → emergency stop, "schémas électriques" → control circuits).
3. **Evaluation**: one rule per requirement, returning a status, a reason and, for ambiguous cases, the missing evidence.
4. **Report**: grouped by status, with the corrective action for each gap.

## Tests

17 tests check the verdict of every requirement on the reference sheet and on modified sheets, to prove the rules react to the evidence:

- adding Italian and Portuguese manuals turns REQ-06 to satisfied;
- a full life-cycle risk assessment turns REQ-08 to satisfied;
- a market whose language the rule does not know (e.g. Belgium) gives *ambiguous*, never a silent *satisfied*.

## Run it

```bash
python audit.py           # Python 3.10+, standard library only
pip install pytest && pytest tests
```

---

Alaa Eddine Tahir, engineering student at Arts et Métiers. [LinkedIn](https://linkedin.com/in/alaaeddine-tahir)
