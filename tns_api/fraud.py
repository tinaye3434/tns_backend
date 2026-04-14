import pickle
from collections import defaultdict, deque
from datetime import timedelta
from typing import Iterable, List, Dict, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest

from .models import Claim, FraudModelSnapshot, FraudScore

FEATURE_COLUMNS = [
    "claim_total",
    "claims_last_30d",
    "claims_last_90d",
    "days_since_last_claim",
    "claim_duration_days",
]


def training_quality(row_count: int) -> Dict[str, str | int]:
    if row_count < 300:
        return {"quality": "low", "threshold": 300}
    if row_count < 2000:
        return {"quality": "medium", "threshold": 2000}
    return {"quality": "high", "threshold": 2000}


def _claim_duration_days(claim: Claim) -> float:
    if not claim.departure_date or not claim.return_date:
        return 0.0
    delta = claim.return_date - claim.departure_date
    if delta.total_seconds() <= 0:
        return 0.0
    return float(max(1, delta.days + (1 if delta.seconds > 0 else 0)))


def _build_history_maps(claims: Iterable[Claim]) -> Dict[int, Dict[str, float]]:
    employee_ids = {claim.employee_id for claim in claims if claim.employee_id is not None}
    history_map: Dict[int, Dict[str, float]] = {}
    if not employee_ids:
        return history_map

    all_claims = (
        Claim.objects.filter(employee_id__in=employee_ids, departure_date__isnull=False)
        .order_by("employee_id", "departure_date", "id")
    )

    grouped: Dict[int, List[Claim]] = defaultdict(list)
    for claim in all_claims:
        grouped[int(claim.employee_id)].append(claim)

    for employee_id, items in grouped.items():
        window_30 = deque()
        window_90 = deque()
        last_date = None

        for claim in items:
            current_date = claim.departure_date
            if not current_date:
                continue

            while window_30 and (current_date - window_30[0]) > timedelta(days=30):
                window_30.popleft()
            while window_90 and (current_date - window_90[0]) > timedelta(days=90):
                window_90.popleft()

            days_since = 999.0
            if last_date:
                days_since = float((current_date - last_date).days)

            history_map[int(claim.id)] = {
                "claims_last_30d": float(len(window_30)),
                "claims_last_90d": float(len(window_90)),
                "days_since_last_claim": days_since,
            }

            window_30.append(current_date)
            window_90.append(current_date)
            last_date = current_date

    return history_map


def build_feature_matrix(claims: Iterable[Claim]) -> Tuple[np.ndarray, List[int]]:
    claims = list(claims)
    if not claims:
        return np.empty((0, len(FEATURE_COLUMNS)), dtype=float), []

    claim_ids = [claim.id for claim in claims]

    history_map = _build_history_maps(claims)

    feature_rows: List[List[float]] = []
    claim_id_order: List[int] = []

    for claim in claims:
        history = history_map.get(int(claim.id), {
            "claims_last_30d": 0.0,
            "claims_last_90d": 0.0,
            "days_since_last_claim": 999.0,
        })

        feature_rows.append(
            [
                float(claim.total or 0.0),
                float(history["claims_last_30d"]),
                float(history["claims_last_90d"]),
                float(history["days_since_last_claim"]),
                float(_claim_duration_days(claim)),
            ]
        )
        claim_id_order.append(int(claim.id))

    return np.array(feature_rows, dtype=float), claim_id_order


def _fit_scaler(x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    means = np.nanmean(x, axis=0)
    stds = np.nanstd(x, axis=0)
    stds = np.where(stds == 0, 1.0, stds)
    return means, stds


def _apply_scaler(x: np.ndarray, means: np.ndarray, stds: np.ndarray) -> np.ndarray:
    return (x - means) / stds


def _train_and_persist(
    x: np.ndarray,
    feature_columns: List[str],
    trained_from=None,
    trained_to=None,
) -> FraudModelSnapshot:
    means, stds = _fit_scaler(x)
    x_scaled = _apply_scaler(x, means, stds)

    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42,
    )
    model.fit(x_scaled)

    raw_scores = -model.decision_function(x_scaled)
    p05 = float(np.percentile(raw_scores, 5))
    p95 = float(np.percentile(raw_scores, 95))

    snapshot = FraudModelSnapshot.objects.create(
        model_blob=pickle.dumps(model),
        feature_columns=feature_columns,
        feature_means=means.tolist(),
        feature_stds=stds.tolist(),
        score_p05=p05,
        score_p95=p95,
        training_rows=int(x.shape[0]),
        trained_from=trained_from,
        trained_to=trained_to,
    )

    return snapshot


def train_fraud_model(
    trained_from=None,
    trained_to=None,
) -> FraudModelSnapshot:
    queryset = Claim.objects.all().order_by("id")
    if trained_from:
        queryset = queryset.filter(departure_date__gte=trained_from)
    if trained_to:
        queryset = queryset.filter(departure_date__lte=trained_to)

    claims = list(queryset)
    if not claims:
        raise ValueError("No claims available for training.")

    x, _ = build_feature_matrix(claims)
    return _train_and_persist(x, FEATURE_COLUMNS, trained_from=trained_from, trained_to=trained_to)


def train_fraud_model_from_matrix(
    x: np.ndarray,
    feature_columns: List[str],
    trained_from=None,
    trained_to=None,
) -> FraudModelSnapshot:
    if x.size == 0:
        raise ValueError("No rows available for training.")
    if x.ndim != 2:
        raise ValueError("Training matrix must be 2-dimensional.")
    if x.shape[1] != len(feature_columns):
        raise ValueError("Feature columns do not match training data width.")
    return _train_and_persist(x, feature_columns, trained_from=trained_from, trained_to=trained_to)


def get_latest_model_snapshot() -> FraudModelSnapshot | None:
    return FraudModelSnapshot.objects.order_by("-created_at").first()


def _scale_score(raw: float, p05: float, p95: float) -> float:
    if p95 <= p05:
        return 50.0
    normalized = (raw - p05) / (p95 - p05)
    normalized = max(0.0, min(1.0, normalized))
    return normalized * 100.0


def _risk_level(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"

def _apply_low_total_rule(claim: Claim, score: float, level: str) -> tuple[float, str]:
    if (claim.total or 0.0) < 500:
        return min(score, 39.9), "low"
    return score, level


def score_claims(claims: Iterable[Claim], snapshot: FraudModelSnapshot) -> List[Dict]:
    claims = list(claims)
    if not claims:
        return []

    x, claim_order = build_feature_matrix(claims)

    means = np.array(snapshot.feature_means, dtype=float)
    stds = np.array(snapshot.feature_stds, dtype=float)
    x_scaled = _apply_scaler(x, means, stds)

    model = pickle.loads(snapshot.model_blob)
    raw_scores = -model.decision_function(x_scaled)

    results = []
    for idx, claim_id in enumerate(claim_order):
        raw = float(raw_scores[idx])
        score = _scale_score(raw, snapshot.score_p05, snapshot.score_p95)
        level = _risk_level(score)
        features = {FEATURE_COLUMNS[i]: float(x[idx, i]) for i in range(len(FEATURE_COLUMNS))}

        claim = next((c for c in claims if int(c.id) == int(claim_id)), None)
        if claim is None:
            continue
        score, level = _apply_low_total_rule(claim, score, level)

        FraudScore.objects.update_or_create(
            claim=claim,
            defaults={
                "model_snapshot": snapshot,
                "score": score,
                "raw_score": raw,
                "risk_level": level,
                "features": features,
            },
        )

        results.append(
            {
                "claim_id": claim_id,
                "score": score,
                "raw_score": raw,
                "risk_level": level,
                "features": features,
                "model_snapshot_id": snapshot.id,
            }
        )

    return results


def model_status(snapshot: FraudModelSnapshot | None) -> Dict:
    if not snapshot:
        return {
            "has_model": False,
        }

    return {
        "has_model": True,
        "snapshot_id": snapshot.id,
        "created_at": snapshot.created_at,
        "training_rows": snapshot.training_rows,
        "trained_from": snapshot.trained_from,
        "trained_to": snapshot.trained_to,
        "feature_columns": snapshot.feature_columns,
    }
