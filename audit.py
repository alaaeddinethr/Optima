#!/usr/bin/env python3
"""
audit.py - Outil de vérification de conformité réglementaire
Pipeline : lecture → structuration → comparaison → rapport

Usage : python audit.py
"""

import re
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# 1. MODÈLES DE DONNÉES
# ══════════════════════════════════════════════════════════════════════════════

class Status(str, Enum):
    SATISFAIT     = "SATISFAIT"
    NON_SATISFAIT = "NON SATISFAIT"
    AMBIGU        = "AMBIGU"


@dataclass
class Requirement:
    """Une exigence réglementaire extraite du texte normatif."""
    id:          str
    text:        str
    category:    str
    conditional: bool          = False
    condition:   Optional[str] = None   # condition d'applicabilité (ex : risque élevé)

    def __str__(self) -> str:
        cond = f" [si {self.condition}]" if self.conditional else ""
        return f"[{self.id}]{cond} {self.text}"


@dataclass
class ProductSheet:
    """Fiche produit structurée, prête à la comparaison."""
    # ── Identification ──────────────────────────────────────────────────────
    manufacturer:        str
    signatory_name:      str
    signatory_title:     str   # ex. "Responsable Qualité"
    markets:             list  # ex. ["France", "Italie", "Portugal"]

    # ── Déclaration CE ──────────────────────────────────────────────────────
    ce_declaration_status: str   # "COMPLETE" | "EN_COURS" | "ABSENTE"
    ce_declaration_signed: bool

    # ── Dossier technique ───────────────────────────────────────────────────
    technical_file_complete:  bool
    electrical_schemas:       bool
    pneumatic_schemas:        bool
    hydraulic_schemas:        bool   # False = machine tout-électrique

    # ── Sécurité ────────────────────────────────────────────────────────────
    protection_enclosure:     bool
    emergency_stop_present:   bool
    emergency_stop_standard:  str   # ex. "EN ISO 13850"
    risk_assessment_done:     bool
    risk_assessment_scope:    str   # "utilisation uniquement" | "cycle complet" | …
    risk_category:            str   # "standard" | "elevé"

    # ── Marquage ────────────────────────────────────────────────────────────
    ce_marking_present:   bool
    ce_marking_location:  str   # ex. "tableau de commande" vs "machine"

    # ── Documentation utilisateur ───────────────────────────────────────────
    manual_present:             bool
    manual_languages:           list  # ex. ["français"]
    manual_commissioning:       bool
    manual_maintenance:         bool
    manual_residual_risks:      bool
    manual_residual_risks_note: str   # ex. "OUI, section 8.3 (Entretien et nettoyage)"


@dataclass
class AuditResult:
    """Résultat de l'évaluation d'une exigence."""
    requirement: Requirement
    status:      Status
    reason:      str
    missing:     Optional[str] = None  # Pour AMBIGU : ce qu'il faudrait pour conclure

    def format_short(self) -> str:
        lines = [f"  [{self.requirement.id}] {self.requirement.text}"]
        lines.append(f"    Raison   : {self.reason}")
        if self.missing:
            lines.append(f"    Manquant : {self.missing}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 2. TEXTES SOURCE (embarqués pour portabilité)
# ══════════════════════════════════════════════════════════════════════════════

REGULATORY_TEXT = """\
REQ-01 : Le fabricant doit rédiger une déclaration CE avant mise sur le marché.
REQ-02 : La déclaration CE doit être signée par un représentant habilité.
REQ-03 : La machine doit porter le marquage CE avant commercialisation.
REQ-04 : Le dossier technique doit inclure les schémas des circuits de commande.
REQ-05 : Une notice d'instructions doit accompagner la machine.
REQ-06 : La notice doit être disponible dans la langue de chaque pays de commercialisation.
REQ-07 : La notice doit mentionner explicitement les risques résiduels identifiés.
REQ-08 : Une évaluation des risques couvrant le cycle de vie complet doit être documentée.
REQ-09 : Les éléments mobiles dangereux doivent être protégés par des dispositifs adéquats.
REQ-10 : Un dispositif d'arrêt d'urgence conforme à EN 13850 doit être présent.
REQ-11 : Pour les machines à risque élevé, un organisme notifié doit intervenir.
"""

PRODUCT_TEXT = """\
Fabricant : AutoWeld Technologies SAS
Signataire : Mme Isabelle RENARD, Responsable Qualité
Marchés visés : France, Italie, Portugal

Dossier technique : COMPLET
Schémas électriques et pneumatiques : PRÉSENTS
Note : machine tout-électrique, pas de circuits hydrauliques
Déclaration CE : EN COURS, signature prévue avant livraison

Enceinte de protection avec accès verrouillé : OUI
Bouton STOP d'urgence en façade : OUI, certifié EN ISO 13850
Évaluation des risques : RÉALISÉE pour la phase d'utilisation uniquement
Catégorie de risque : standard (pas de catégorie spéciale)

Marquage CE : OUI, apposé sur le tableau de commande

Notice d'instructions : PRÉSENTE en français
Contenu notice - mise en service : OUI
Contenu notice - maintenance : OUI
Contenu notice - risques résiduels : OUI, section 8.3 (Entretien et nettoyage)
"""

# Catégories des exigences
REQUIREMENT_CATEGORIES = {
    "REQ-01": "declaration_ce",
    "REQ-02": "declaration_ce",
    "REQ-03": "marquage",
    "REQ-04": "dossier_technique",
    "REQ-05": "notice",
    "REQ-06": "notice",
    "REQ-07": "notice",
    "REQ-08": "evaluation_risques",
    "REQ-09": "securite",
    "REQ-10": "securite",
    "REQ-11": "organisme_notifie",
}


# ══════════════════════════════════════════════════════════════════════════════
# 3. PARSING DU TEXTE RÉGLEMENTAIRE
# ══════════════════════════════════════════════════════════════════════════════

def parse_requirements(text: str) -> list:
    """
    Extrait chaque exigence (REQ-XX) via regex, normalise les espaces,
    et enrichit avec métadonnées (catégorie, conditionnalité).
    """
    pattern = re.compile(r"(REQ-\d+)\s*:\s*(.*?)(?=REQ-\d+\s*:|$)", re.DOTALL)
    requirements = []
    for m in pattern.finditer(text):
        req_id   = m.group(1).strip()
        req_text = " ".join(m.group(2).strip().split())  # collapse whitespace
        is_cond  = (req_id == "REQ-11")
        requirements.append(Requirement(
            id          = req_id,
            text        = req_text,
            category    = REQUIREMENT_CATEGORIES.get(req_id, "autre"),
            conditional = is_cond,
            condition   = "machines à risque élevé" if is_cond else None,
        ))
    return requirements


# ══════════════════════════════════════════════════════════════════════════════
# 4. PARSING DE LA FICHE PRODUIT
# ══════════════════════════════════════════════════════════════════════════════

def _get(pattern: str, text: str, default: str = "") -> str:
    """Extrait la première capture d'un motif, ou renvoie default."""
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default


def _is_yes(pattern: str, text: str) -> bool:
    """Renvoie True si la valeur associée au motif commence par OUI/COMPLET/PRÉSENT."""
    val = _get(pattern, text).upper()
    return any(val.startswith(k) for k in ("OUI", "COMPLET", "PR\u00c9SENT", "PRESENT"))


def parse_product_sheet(text: str) -> ProductSheet:
    """
    Parse la fiche produit en un objet structuré.
    Traite explicitement les synonymes et formulations différentes
    (ex. 'EN ISO 13850' vs 'EN 13850', 'Bouton STOP' vs 'arrêt d urgence').
    """
    # ── Identification ──────────────────────────────────────────────────────
    signatory_raw   = _get(r"Signataire\s*:\s*(.+)", text)
    sig_parts       = [s.strip() for s in signatory_raw.split(",")]
    signatory_name  = sig_parts[0] if sig_parts else ""
    signatory_title = sig_parts[1] if len(sig_parts) > 1 else ""

    markets_raw = _get(r"March[eé]s\s+vis[eé]s\s*:\s*(.+)", text)
    markets     = [m.strip() for m in markets_raw.split(",")] if markets_raw else []

    # ── Déclaration CE ──────────────────────────────────────────────────────
    ce_raw = _get(r"D[eé]claration CE\s*:\s*(.+)", text).upper()
    if "EN COURS" in ce_raw:
        ce_status = "EN_COURS"
    elif any(k in ce_raw for k in ("COMPLET", "SIGN\u00c9E", "SIGNEE", "OUI")):
        ce_status = "COMPLETE"
    else:
        ce_status = "ABSENTE"
    ce_signed = (ce_status == "COMPLETE")

    # ── Dossier technique ───────────────────────────────────────────────────
    tech_file_ok  = bool(re.search(r"Dossier technique\s*:\s*COMPLET", text, re.IGNORECASE))
    schemas_ok    = bool(re.search(r"Sch[eé]mas.+?:\s*PR[EÉ]SENTS?", text, re.IGNORECASE))
    no_hydraulics = bool(re.search(r"pas de circuits hydrauliques", text, re.IGNORECASE))

    # ── Sécurité ────────────────────────────────────────────────────────────
    enclosure_ok = bool(re.search(r"Enceinte.+?acc[eè]s verrouill[eé].+?:\s*OUI", text, re.IGNORECASE))

    # "Bouton STOP d'urgence" = synonyme réglementaire de "dispositif d'arrêt d'urgence"
    emg_match    = re.search(
        r"(?:Bouton|Arr[eê]t)\s*(?:STOP|d['\u2019]urgence).+?:\s*OUI(.+)",
        text, re.IGNORECASE
    )
    emg_present  = bool(emg_match)
    emg_suffix   = emg_match.group(1).strip() if emg_match else ""
    std_match    = re.search(r"(EN\s*(?:ISO\s*)?\d{4,5}(?:\s*:\s*\d{4})?)", emg_suffix, re.IGNORECASE)
    emg_standard = std_match.group(1).strip() if std_match else ""

    risk_raw  = _get(r"[EÉ]valuation des risques\s*:\s*(.+)", text)
    risk_done = bool(re.search(r"R[EÉ]ALIS[EÉ]E|OUI", risk_raw, re.IGNORECASE))
    if "utilisation uniquement" in risk_raw.lower():
        risk_scope = "utilisation uniquement"
    elif re.search(r"cycle.*(vie|complet)", risk_raw, re.IGNORECASE):
        risk_scope = "cycle complet"
    else:
        risk_scope = "non précisé"

    risk_cat_raw = _get(r"Cat[eé]gorie de risque\s*:\s*(.+)", text).lower()
    risk_cat     = "elevé" if re.search(r"[eé]lev[eé]|haute", risk_cat_raw) else "standard"

    # ── Marquage CE ─────────────────────────────────────────────────────────
    ce_mark_raw     = _get(r"Marquage CE\s*:\s*(.+)", text)
    ce_mark_present = bool(re.search(r"OUI", ce_mark_raw, re.IGNORECASE))
    if "tableau de commande" in ce_mark_raw.lower():
        ce_mark_loc = "tableau de commande"
    elif re.search(r"machine|ch[aâ]ssis|carcasse", ce_mark_raw, re.IGNORECASE):
        ce_mark_loc = "machine"
    else:
        ce_mark_loc = "non précisé"

    # ── Documentation utilisateur ───────────────────────────────────────────
    notice_raw     = _get(r"Notice d['\u2019]instructions\s*:\s*(.+)", text)
    manual_present = bool(re.search(r"PR[EÉ]SENTE|OUI", notice_raw, re.IGNORECASE))
    lang_hits      = re.findall(
        r"\b(fran[cç]ais|anglais|allemand|italien|portugais|espagnol)\b",
        notice_raw, re.IGNORECASE
    )
    manual_langs = [l.lower() for l in lang_hits]

    residual_raw = _get(r"risques r[eé]siduels\s*:\s*(.+)", text)
    residual_ok  = bool(re.search(r"OUI", residual_raw, re.IGNORECASE))

    return ProductSheet(
        manufacturer            = _get(r"Fabricant\s*:\s*(.+)", text),
        signatory_name          = signatory_name,
        signatory_title         = signatory_title,
        markets                 = markets,
        ce_declaration_status   = ce_status,
        ce_declaration_signed   = ce_signed,
        technical_file_complete = tech_file_ok,
        electrical_schemas      = schemas_ok,
        pneumatic_schemas       = schemas_ok,
        hydraulic_schemas       = not no_hydraulics,
        protection_enclosure    = enclosure_ok,
        emergency_stop_present  = emg_present,
        emergency_stop_standard = emg_standard,
        risk_assessment_done    = risk_done,
        risk_assessment_scope   = risk_scope,
        risk_category           = risk_cat,
        ce_marking_present      = ce_mark_present,
        ce_marking_location     = ce_mark_loc,
        manual_present          = manual_present,
        manual_languages        = manual_langs,
        manual_commissioning    = _is_yes(r"mise en service\s*:\s*(.+)", text),
        manual_maintenance      = _is_yes(r"maintenance\s*:\s*(.+)", text),
        manual_residual_risks   = residual_ok,
        manual_residual_risks_note = residual_raw,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 5. MOTEUR DE COMPARAISON — une fonction par exigence
#    Chaque évaluateur retourne un AuditResult avec un raisonnement explicite.
# ══════════════════════════════════════════════════════════════════════════════

def _result(req, status, reason, missing=None) -> AuditResult:
    return AuditResult(requirement=req, status=status, reason=reason, missing=missing)


def _normalize_standard(s: str) -> str:
    """Normalise un numéro de norme : retire espaces et 'ISO' pour comparaison.
    EN 13850 == EN ISO 13850 (mise à jour de nomenclature internationale).
    """
    return re.sub(r"[\s\-]|ISO", "", s.upper())


def evaluate_req01(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-01 : Déclaration CE rédigée avant mise sur le marché."""
    if p.ce_declaration_status == "COMPLETE":
        return _result(req, Status.SATISFAIT, "Déclaration CE complète et disponible.")
    if p.ce_declaration_status == "EN_COURS":
        return _result(
            req, Status.AMBIGU,
            "Déclaration CE en cours de rédaction — non finalisée à ce stade.",
            missing="Confirmer la finalisation avant toute mise sur le marché."
        )
    return _result(req, Status.NON_SATISFAIT, "Aucune déclaration CE trouvée dans la fiche.")


def evaluate_req02(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-02 : Déclaration CE signée par un représentant habilité."""
    if p.ce_declaration_signed:
        habilite = bool(re.search(
            r"directeur|PDG|DG|habilit[eé]|mandataire|g[eé]rant",
            p.signatory_title, re.IGNORECASE
        ))
        if habilite:
            return _result(req, Status.SATISFAIT,
                           f"Signé par {p.signatory_name} ({p.signatory_title}).")
        return _result(
            req, Status.AMBIGU,
            f"Signataire : {p.signatory_name} ({p.signatory_title}). "
            "Le titre ne mentionne pas explicitement une habilitation.",
            missing="Confirmer que le Responsable Qualité est mandaté pour signer la déclaration CE."
        )
    # Déclaration non encore signée
    return _result(
        req, Status.AMBIGU,
        f"Signataire identifié ({p.signatory_name}, {p.signatory_title}), "
        "mais la déclaration CE n'est pas encore signée (statut : EN COURS).",
        missing="Signature effective de la déclaration par un représentant dûment habilité."
    )


def evaluate_req03(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-03 : Marquage CE apposé sur la machine avant commercialisation."""
    if not p.ce_marking_present:
        return _result(req, Status.NON_SATISFAIT, "Marquage CE absent.")
    if p.ce_marking_location == "machine":
        return _result(req, Status.SATISFAIT, "Marquage CE apposé sur la machine.")
    # Présent mais seulement sur le tableau de commande
    return _result(
        req, Status.AMBIGU,
        f"Marquage CE présent mais apposé sur le '{p.ce_marking_location}', "
        "pas directement sur le corps de la machine.",
        missing="Vérifier si un marquage sur le tableau de commande est réglementairement "
                "suffisant, ou apposer le marquage sur la machine elle-même."
    )


def evaluate_req04(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-04 : Dossier technique incluant les schémas des circuits de commande."""
    if not p.technical_file_complete:
        return _result(req, Status.NON_SATISFAIT, "Dossier technique non complet.")
    if p.electrical_schemas:
        note = (" (machine tout-électrique : absence de schémas hydrauliques justifiée)"
                if not p.hydraulic_schemas else "")
        return _result(req, Status.SATISFAIT,
                       f"Dossier complet, schémas des circuits présents{note}.")
    return _result(req, Status.NON_SATISFAIT,
                   "Dossier technique complet mais schémas des circuits introuvables.")


def evaluate_req05(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-05 : Notice d'instructions accompagnant la machine."""
    if p.manual_present:
        return _result(req, Status.SATISFAIT, "Notice d'instructions présente.")
    return _result(req, Status.NON_SATISFAIT, "Aucune notice d'instructions mentionnée.")


def evaluate_req06(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-06 : Notice disponible dans la langue de chaque pays de commercialisation."""
    COUNTRY_LANG = {
        "france":    "français",
        "italie":    "italien",
        "portugal":  "portugais",
        "espagne":   "espagnol",
        "allemagne": "allemand",
    }
    required_langs = {COUNTRY_LANG[m.lower()] for m in p.markets if m.lower() in COUNTRY_LANG}
    available_langs = {l.lower() for l in p.manual_languages}
    missing_langs   = required_langs - available_langs

    if not missing_langs:
        return _result(req, Status.SATISFAIT,
                       f"Notice disponible dans toutes les langues requises : "
                       f"{', '.join(sorted(required_langs))}.")
    return _result(
        req, Status.NON_SATISFAIT,
        f"Notice uniquement disponible en : {', '.join(sorted(available_langs)) or 'langue non précisée'}. "
        f"Marchés visés : {', '.join(p.markets)}.",
        missing=f"Traductions manquantes : {', '.join(sorted(missing_langs))}."
    )


def evaluate_req07(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-07 : Notice mentionnant explicitement les risques résiduels."""
    if not p.manual_residual_risks:
        return _result(req, Status.NON_SATISFAIT,
                       "Aucune mention des risques résiduels dans la notice.")
    note = p.manual_residual_risks_note.lower()
    if re.search(r"entretien|nettoyage|maintenance", note):
        return _result(
            req, Status.AMBIGU,
            "Risques résiduels mentionnés en section 8.3 intitulée 'Entretien et nettoyage'. "
            "Le placement dans une section de maintenance suggère une couverture partielle.",
            missing="Confirmer que TOUS les risques résiduels identifiés (pas seulement ceux "
                    "liés à l'entretien) sont couverts. Une section dédiée renforcerait la conformité."
        )
    return _result(req, Status.SATISFAIT,
                   f"Risques résiduels explicitement mentionnés ({p.manual_residual_risks_note}).")


def evaluate_req08(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-08 : Évaluation des risques couvrant le cycle de vie complet."""
    if not p.risk_assessment_done:
        return _result(req, Status.NON_SATISFAIT, "Aucune évaluation des risques documentée.")
    if p.risk_assessment_scope == "cycle complet":
        return _result(req, Status.SATISFAIT, "Évaluation couvrant le cycle de vie complet.")
    return _result(
        req, Status.NON_SATISFAIT,
        f"Évaluation réalisée mais limitée à : '{p.risk_assessment_scope}'. "
        "Le cycle de vie complet (conception, installation, utilisation, "
        "maintenance, démantèlement) n'est pas couvert."
    )


def evaluate_req09(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-09 : Éléments mobiles dangereux protégés par des dispositifs adéquats."""
    if p.protection_enclosure:
        return _result(req, Status.SATISFAIT,
                       "Enceinte de protection avec accès verrouillé présente.")
    return _result(req, Status.NON_SATISFAIT,
                   "Aucun dispositif de protection des éléments mobiles mentionné.")


def evaluate_req10(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-10 : Dispositif d'arrêt d'urgence conforme à EN 13850."""
    if not p.emergency_stop_present:
        return _result(req, Status.NON_SATISFAIT, "Aucun dispositif d'arrêt d'urgence mentionné.")

    # Normalisation : EN 13850 == EN ISO 13850 (même norme, nomenclature ISO actualisée)
    required = _normalize_standard("EN13850")
    declared = _normalize_standard(p.emergency_stop_standard)

    if required in declared or declared in required:
        return _result(
            req, Status.SATISFAIT,
            f"Arrêt d'urgence présent, certifié '{p.emergency_stop_standard}' "
            "(équivalent à EN 13850 — nomenclature ISO mise à jour)."
        )
    if p.emergency_stop_standard:
        return _result(
            req, Status.AMBIGU,
            f"Arrêt d'urgence présent, certifié '{p.emergency_stop_standard}'. "
            "Correspondance avec EN 13850 à vérifier explicitement.",
            missing=f"Confirmer l'équivalence entre '{p.emergency_stop_standard}' et EN 13850."
        )
    return _result(req, Status.AMBIGU,
                   "Arrêt d'urgence présent mais aucune norme de certification indiquée.",
                   missing="Fournir la référence normative du dispositif d'arrêt d'urgence.")


def evaluate_req11(req: Requirement, p: ProductSheet) -> AuditResult:
    """REQ-11 : Pour les machines à risque élevé, intervention d'un organisme notifié."""
    if p.risk_category == "elevé":
        return _result(req, Status.NON_SATISFAIT,
                       "Machine à risque élevé : aucun organisme notifié mentionné.")
    # Machine déclarée "standard" → exigence a priori non déclenchée.
    # MAIS : l'évaluation des risques est incomplète (REQ-08) → catégorisation non vérifiable.
    if p.risk_assessment_scope != "cycle complet":
        return _result(
            req, Status.AMBIGU,
            "Machine auto-classée 'standard' (organisme notifié a priori non requis), "
            "mais l'évaluation des risques ne couvre que la phase d'utilisation. "
            "La catégorisation de risque n'est pas pleinement vérifiable.",
            missing="Compléter l'évaluation des risques sur le cycle de vie complet "
                    "avant de confirmer définitivement la catégorie 'standard'."
        )
    return _result(req, Status.SATISFAIT,
                   "Machine à risque standard : organisme notifié non requis.")


# Registre des évaluateurs (dispatch table)
EVALUATORS = {
    "REQ-01": evaluate_req01,
    "REQ-02": evaluate_req02,
    "REQ-03": evaluate_req03,
    "REQ-04": evaluate_req04,
    "REQ-05": evaluate_req05,
    "REQ-06": evaluate_req06,
    "REQ-07": evaluate_req07,
    "REQ-08": evaluate_req08,
    "REQ-09": evaluate_req09,
    "REQ-10": evaluate_req10,
    "REQ-11": evaluate_req11,
}


def evaluate_all(requirements: list, product: ProductSheet) -> list:
    """Applique l'évaluateur correspondant à chaque exigence."""
    results = []
    for req in requirements:
        evaluator = EVALUATORS.get(req.id)
        if evaluator:
            results.append(evaluator(req, product))
        else:
            results.append(_result(
                req, Status.AMBIGU,
                "Aucun évaluateur défini pour cette exigence.",
                missing="Implémenter l'évaluateur correspondant."
            ))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# 6. GÉNÉRATION DU RAPPORT
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(results: list, product: ProductSheet) -> str:
    by_status = {s: [] for s in Status}
    for r in results:
        by_status[r.status].append(r)

    total = len(results)
    n_ok  = len(by_status[Status.SATISFAIT])
    n_nok = len(by_status[Status.NON_SATISFAIT])
    n_amb = len(by_status[Status.AMBIGU])

    sep  = "─" * 62
    wide = "═" * 62

    lines = [
        wide,
        f"  RAPPORT D'AUDIT — {product.manufacturer}",
        wide,
        f"  Satisfait     : {n_ok:2d} / {total}",
        f"  Non satisfait : {n_nok:2d} / {total}",
        f"  Ambigu        : {n_amb:2d} / {total}",
        sep,
    ]

    if by_status[Status.NON_SATISFAIT]:
        lines.append("\nNON SATISFAIT :")
        for r in by_status[Status.NON_SATISFAIT]:
            lines.append(r.format_short())

    if by_status[Status.AMBIGU]:
        lines.append("\nAMBIGU (information présente mais insuffisante pour conclure) :")
        for r in by_status[Status.AMBIGU]:
            lines.append(r.format_short())

    if by_status[Status.SATISFAIT]:
        lines.append("\nSATISFAIT :")
        for r in by_status[Status.SATISFAIT]:
            lines.append(r.format_short())

    lines.append("\n" + wide)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 7. POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("Chargement du texte réglementaire…")
    requirements = parse_requirements(REGULATORY_TEXT)
    print(f"  → {len(requirements)} exigences extraites.\n")

    print("Chargement de la fiche produit…")
    product = parse_product_sheet(PRODUCT_TEXT)
    print(f"  → Produit    : {product.manufacturer}")
    print(f"  → Marchés    : {', '.join(product.markets)}")
    print(f"  → Signataire : {product.signatory_name} ({product.signatory_title})\n")

    print("Comparaison en cours…\n")
    results = evaluate_all(requirements, product)

    report = generate_report(results, product)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
