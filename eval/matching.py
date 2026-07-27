"""
Matching logic between pipeline predictions and gold annotations.

Claims:        same paper_id + fuzzy statement ratio >= 0.6, greedy 1-to-1.
Contradictions: primary match at the unordered paper-pair level; predictions
               on pairs not labeled in gold are excluded from precision/recall
               (reported as "unlabeled volume"); hits on gold NEGATIVE pairs
               are explicit false positives. A stricter claim-level match is
               reported secondarily.
Gaps:          gap_type must match AND (fuzzy description ratio >= 0.5 OR at
               least 2 gold keywords appear in the predicted description).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Any, FrozenSet

CLAIM_SIM_THRESHOLD = 0.6
GAP_SIM_THRESHOLD = 0.5


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (text or "").lower())).strip()


def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# --------------------------------------------------------------------- #
# Claims                                                                #
# --------------------------------------------------------------------- #

def match_claims(predicted: List[Dict[str, Any]],
                 gold: List[Dict[str, Any]],
                 threshold: float = CLAIM_SIM_THRESHOLD) -> Dict[str, Any]:
    """Greedy one-to-one matching of predicted to gold claims.

    Each claim dict needs: paper_id, statement.
    """
    candidates = []
    for pi, pred in enumerate(predicted):
        for gi, gold_claim in enumerate(gold):
            if pred.get("paper_id") != gold_claim.get("paper_id"):
                continue
            ratio = fuzzy_ratio(pred.get("statement", ""), gold_claim.get("statement", ""))
            if ratio >= threshold:
                candidates.append((ratio, pi, gi))

    candidates.sort(reverse=True)
    matched_pred, matched_gold, pairs = set(), set(), []
    for ratio, pi, gi in candidates:
        if pi in matched_pred or gi in matched_gold:
            continue
        matched_pred.add(pi)
        matched_gold.add(gi)
        pairs.append({"pred_index": pi, "gold_index": gi, "similarity": round(ratio, 3)})

    tp = len(pairs)
    fp = len(predicted) - tp
    fn = len(gold) - tp
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": tp / len(predicted) if predicted else 0.0,
        "recall": tp / len(gold) if gold else 0.0,
        "f1": (2 * tp / (len(predicted) + len(gold))
               if (predicted or gold) else 0.0),
        "matches": pairs,
        "missed_gold_indices": [i for i in range(len(gold)) if i not in matched_gold],
    }


# --------------------------------------------------------------------- #
# Contradictions                                                        #
# --------------------------------------------------------------------- #

def _paper_pair(entry: Dict[str, Any]) -> FrozenSet[str]:
    return frozenset({str(entry.get("paper_id_1") or entry.get("paper1_id")),
                      str(entry.get("paper_id_2") or entry.get("paper2_id"))})


def match_contradictions(predicted: List[Dict[str, Any]],
                         gold: Dict[str, List[Dict[str, Any]]],
                         claim_threshold: float = CLAIM_SIM_THRESHOLD) -> Dict[str, Any]:
    """Match predicted contradictions against gold positives/negatives.

    Predicted entries need paper1_id/paper2_id (or paper_id_1/paper_id_2) and
    optionally claim texts (evidence_claim1/evidence_claim2 or claim_text_*).
    Gold: {"positives": [...], "negatives": [...]} in the schema from
    eval/README.md.
    """
    gold_pos = gold.get("positives", [])
    gold_neg = gold.get("negatives", [])
    pos_pairs = {_paper_pair(g): g for g in gold_pos}
    neg_pairs = {_paper_pair(g) for g in gold_neg}

    tp_pairs, fp_on_negatives, unlabeled = [], [], []
    strict_tp = 0
    for pred in predicted:
        pair = _paper_pair(pred)
        if pair in pos_pairs:
            tp_pairs.append(pred)
            gold_entry = pos_pairs[pair]
            if _claims_match_strict(pred, gold_entry, claim_threshold):
                strict_tp += 1
        elif pair in neg_pairs:
            fp_on_negatives.append(pred)
        else:
            unlabeled.append(pred)

    found_pairs = {_paper_pair(p) for p in tp_pairs}
    missed = [g for g in gold_pos if _paper_pair(g) not in found_pairs]

    tp = len(found_pairs & set(pos_pairs))
    labeled_predictions = tp + len(fp_on_negatives)
    return {
        "pair_level": {
            "tp": tp,
            "fp_on_negatives": len(fp_on_negatives),
            "fn": len(missed),
            "precision_on_labeled": (tp / labeled_predictions
                                     if labeled_predictions else None),
            "recall": tp / len(gold_pos) if gold_pos else None,
            "false_positive_rate_on_negatives": (len(fp_on_negatives) / len(gold_neg)
                                                 if gold_neg else None),
        },
        "claim_level_strict": {
            "tp": strict_tp,
            "recall": strict_tp / len(gold_pos) if gold_pos else None,
        },
        "unlabeled_prediction_volume": len(unlabeled),
        "missed_gold": missed,
        "false_positives_on_negatives": fp_on_negatives,
        "unlabeled_predictions": unlabeled,
    }


def _claims_match_strict(pred: Dict[str, Any], gold_entry: Dict[str, Any],
                         threshold: float) -> bool:
    pred_1 = pred.get("claim_text_1") or pred.get("evidence_claim1") or ""
    pred_2 = pred.get("claim_text_2") or pred.get("evidence_claim2") or ""
    gold_1 = gold_entry.get("claim_text_1", "")
    gold_2 = gold_entry.get("claim_text_2", "")
    if not (pred_1 and pred_2 and gold_1 and gold_2):
        return False
    straight = (fuzzy_ratio(pred_1, gold_1) >= threshold and
                fuzzy_ratio(pred_2, gold_2) >= threshold)
    crossed = (fuzzy_ratio(pred_1, gold_2) >= threshold and
               fuzzy_ratio(pred_2, gold_1) >= threshold)
    return straight or crossed


# --------------------------------------------------------------------- #
# Gaps                                                                  #
# --------------------------------------------------------------------- #

def _gap_matches(pred: Dict[str, Any], gold_gap: Dict[str, Any]) -> bool:
    if pred.get("gap_type") != gold_gap.get("gap_type"):
        return False
    if fuzzy_ratio(pred.get("description", ""),
                   gold_gap.get("description", "")) >= GAP_SIM_THRESHOLD:
        return True
    pred_text = normalize(pred.get("description", ""))
    keywords = [normalize(k) for k in gold_gap.get("keywords", [])]
    hits = sum(1 for k in keywords if k and k in pred_text)
    return hits >= 2


def match_gaps(predicted: List[Dict[str, Any]],
               gold: List[Dict[str, Any]],
               ks: tuple = (3, 5)) -> Dict[str, Any]:
    """Precision@k and recall for ranked gap predictions.

    `predicted` must be in rank order (rank 1 first).
    """
    per_pred = []
    matched_gold = set()
    for pred in predicted:
        match_index = None
        for gi, gold_gap in enumerate(gold):
            if gi in matched_gold:
                continue
            if _gap_matches(pred, gold_gap):
                match_index = gi
                matched_gold.add(gi)
                break
        per_pred.append({"description": pred.get("description", ""),
                         "gap_type": pred.get("gap_type", ""),
                         "matched_gold_index": match_index})

    result: Dict[str, Any] = {
        "recall": len(matched_gold) / len(gold) if gold else None,
        "per_prediction": per_pred,
        "missed_gold_indices": [i for i in range(len(gold)) if i not in matched_gold],
    }
    for k in ks:
        top = per_pred[:k]
        hits = sum(1 for p in top if p["matched_gold_index"] is not None)
        result[f"precision_at_{k}"] = hits / len(top) if top else None
    return result
