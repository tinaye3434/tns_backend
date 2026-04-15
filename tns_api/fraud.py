import pickle
from collections import defaultdict, deque
from datetime import timedelta
from typing import Iterable, List, Dict, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest
from django.utils import timezone

from .models import Claim, ClaimLine, FraudModelSnapshot, FraudScore, GPSValidation, OCRResult

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


RULE_WEIGHTS = {
    "monthly_days_exceeded": 30.0,
    "monthly_trip_count_exceeded": 20.0,
    "high_monthly_trip_count": 15.0,
    "repeated_same_route": 15.0,
    "claims_too_close_together": 15.0,
    "mileage_anomaly": 35.0,
    "weekend_concentration": 10.0,
    "repeated_receipt_amounts": 15.0,
    "claim_total_above_employee_norm": 20.0,
    "claim_total_far_above_employee_norm": 15.0,
    "short_trip_high_amount": 25.0,
    "multiple_same_day_claims": 15.0,
    "delayed_or_missing_receipts": 20.0,
    "threshold_gaming": 30.0,
}

HIGH_SEVERITY_RULES = {
    "monthly_days_exceeded",
    "high_monthly_trip_count",
    "mileage_anomaly",
    "claim_total_far_above_employee_norm",
    "short_trip_high_amount",
    "delayed_or_missing_receipts",
    "threshold_gaming",
}

AUTO_APPROVE_HARD_STOPS = {
    "monthly_days_exceeded",
    "high_monthly_trip_count",
    "mileage_anomaly",
    "delayed_or_missing_receipts",
    "threshold_gaming",
    "short_trip_high_amount",
}


def _month_bounds(dt):
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _safe_float(value, default=0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _claim_day_span(claim: Claim) -> float:
    return float(claim.days or _claim_duration_days(claim) or 0.0)


def _build_rule_flags(claim: Claim) -> List[Dict[str, object]]:
    if not claim.departure_date:
        return []

    flags: List[Dict[str, object]] = []
    month_start, month_end = _month_bounds(claim.departure_date)
    employee_claims = list(
        Claim.objects.filter(employee_id=claim.employee_id)
        .exclude(id=claim.id)
        .order_by("departure_date", "id")
    )
    monthly_claims = [
        item
        for item in employee_claims
        if item.departure_date and month_start <= item.departure_date < month_end
    ]
    monthly_days = sum(_claim_day_span(item) for item in monthly_claims) + _claim_day_span(claim)
    monthly_trip_count = len(monthly_claims) + 1

    if monthly_days > 12:
        flags.append(
            {
                "code": "monthly_days_exceeded",
                "severity": "high",
                "message": f"Monthly claimed days reached {monthly_days:.1f}, above the limit of 12.",
            }
        )

    if monthly_trip_count > 2:
        severity = "high" if monthly_trip_count > 4 else "medium"
        flags.append(
            {
                "code": "high_monthly_trip_count" if severity == "high" else "monthly_trip_count_exceeded",
                "severity": severity,
                "message": f"Employee has {monthly_trip_count} trips in the same month.",
            }
        )

    recent_30d = [
        item
        for item in employee_claims
        if item.departure_date and 0 <= (claim.departure_date - item.departure_date).days <= 30
    ]
    same_route_count = sum(
        1
        for item in recent_30d
        if (item.origin or "").strip().lower() == (claim.origin or "").strip().lower()
        and (item.destination or "").strip().lower() == (claim.destination or "").strip().lower()
    )
    if same_route_count >= 3:
        flags.append(
            {
                "code": "repeated_same_route",
                "severity": "medium",
                "message": f"Same route repeated {same_route_count + 1} times in 30 days.",
            }
        )

    previous_claims = [item for item in employee_claims if item.departure_date and item.departure_date < claim.departure_date]
    if previous_claims:
        previous = previous_claims[-1]
        gap_days = (claim.departure_date - previous.departure_date).days
        if gap_days < 3:
            flags.append(
                {
                    "code": "claims_too_close_together",
                    "severity": "medium",
                    "message": f"Only {gap_days} day(s) since the previous claim.",
                }
            )

    gps_validation = GPSValidation.objects.filter(claim=claim).first()
    variance_pct = _safe_float(getattr(gps_validation, "variance_pct", None))
    if variance_pct > 0.15:
        flags.append(
            {
                "code": "mileage_anomaly",
                "severity": "high",
                "message": f"Mileage variance is {variance_pct * 100:.1f}%, above the 15% threshold.",
            }
        )

    weekend_claims = sum(
        1
        for item in recent_30d
        if item.departure_date and item.departure_date.weekday() >= 5
    )
    if claim.departure_date.weekday() >= 5 and weekend_claims >= 2:
        flags.append(
            {
                "code": "weekend_concentration",
                "severity": "medium",
                "message": "Repeated weekend claim departures detected in the last 30 days.",
            }
        )

    prior_totals = [_safe_float(item.total) for item in employee_claims if item.total is not None]
    if prior_totals:
        average_total = sum(prior_totals) / len(prior_totals)
        claim_total = _safe_float(claim.total)
        if average_total > 0 and claim_total > average_total * 2.5:
            flags.append(
                {
                    "code": "claim_total_far_above_employee_norm",
                    "severity": "high",
                    "message": f"Claim total is more than 2.5x the employee average of {average_total:.2f}.",
                }
            )
        elif average_total > 0 and claim_total > average_total * 1.75:
            flags.append(
                {
                    "code": "claim_total_above_employee_norm",
                    "severity": "medium",
                    "message": f"Claim total is more than 1.75x the employee average of {average_total:.2f}.",
                }
            )

    if _claim_day_span(claim) <= 1 and _safe_float(claim.total) > 800:
        flags.append(
            {
                "code": "short_trip_high_amount",
                "severity": "high",
                "message": "Short trip with unusually high claim total.",
            }
        )

    same_day_count = sum(
        1
        for item in employee_claims
        if item.departure_date and item.departure_date.date() == claim.departure_date.date()
    )
    if same_day_count >= 1:
        flags.append(
            {
                "code": "multiple_same_day_claims",
                "severity": "medium",
                "message": "Multiple claims share the same departure day.",
            }
        )

    if claim.return_date and not claim.documents_submitted:
        overdue_days = (timezone.now() - claim.return_date).days
        if overdue_days > 3:
            flags.append(
                {
                    "code": "delayed_or_missing_receipts",
                    "severity": "high",
                    "message": f"Receipts are overdue by {overdue_days} day(s).",
                }
            )

    threshold_gaming_count = sum(
        1
        for item in recent_30d
        if 450 <= _safe_float(item.total) <= 500
    )
    if 450 <= _safe_float(claim.total) <= 500 and threshold_gaming_count >= 2:
        flags.append(
            {
                "code": "threshold_gaming",
                "severity": "high",
                "message": "Multiple claims are clustered just below the easy-approval threshold.",
            }
        )

    recent_claim_ids = [item.id for item in recent_30d if item.id]
    if recent_claim_ids:
        claim_line_ids = list(
            ClaimLine.objects.filter(claim_id__in=recent_claim_ids).values_list("id", flat=True)
        )
        if claim_line_ids:
            amounts = list(
                OCRResult.objects.filter(receipt__claim_line_id__in=claim_line_ids, total_amount__isnull=False)
                .values_list("total_amount", flat=True)
            )
            repeated_amounts = defaultdict(int)
            for amount in amounts:
                rounded = round(_safe_float(amount), 2)
                repeated_amounts[rounded] += 1
            if repeated_amounts and max(repeated_amounts.values()) >= 3:
                flags.append(
                    {
                        "code": "repeated_receipt_amounts",
                        "severity": "medium",
                        "message": "Receipt totals repeat unusually often across recent claims.",
                    }
                )

    return flags


def _combine_scores(claim: Claim, model_score: float) -> tuple[float, str, List[Dict[str, object]], bool, bool]:
    flags = _build_rule_flags(claim)
    total = _safe_float(claim.total)
    hard_stop = any(flag["code"] in AUTO_APPROVE_HARD_STOPS for flag in flags)
    auto_approve = total <= 500 and not hard_stop

    if auto_approve:
        flags.insert(
            0,
            {
                "code": "low_total_auto_approve",
                "severity": "info",
                "message": "Claim total is 500 or less and no hard-stop rules were triggered.",
            },
        )
        return 10.0, "low", flags, True, False

    rule_penalty = sum(RULE_WEIGHTS.get(str(flag["code"]), 0.0) for flag in flags)
    medium_flags = sum(1 for flag in flags if flag["severity"] == "medium")
    high_flags = sum(1 for flag in flags if flag["severity"] == "high")
    final_score = max(0.0, min(100.0, model_score + rule_penalty))
    final_level = _risk_level(final_score)

    if high_flags >= 1 or medium_flags >= 2:
        final_level = "high" if high_flags >= 1 else "medium"
        final_score = max(final_score, 70.0 if high_flags >= 1 else 45.0)

    manual_review = high_flags >= 1 or medium_flags >= 2
    return final_score, final_level, flags, False, manual_review


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
        base_features = {FEATURE_COLUMNS[i]: float(x[idx, i]) for i in range(len(FEATURE_COLUMNS))}

        claim = next((c for c in claims if int(c.id) == int(claim_id)), None)
        if claim is None:
            continue
        score, level, rule_flags, auto_approve, manual_review = _combine_scores(claim, score)
        features = {
            **base_features,
            "rule_flags": rule_flags,
            "auto_approve": auto_approve,
            "manual_review_required": manual_review,
        }

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
                "rule_flags": rule_flags,
                "auto_approve": auto_approve,
                "manual_review_required": manual_review,
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
