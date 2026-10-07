def calculate_priority_score(
    critical: int,
    serious: int,
    moderate: int,
    area_risk: float = 0.2,
    wait_minutes: float = 0.0
) -> tuple[float, str]:
    wait_capped = min(float(wait_minutes), 30.0)
    score = (
        critical * 3.0 +
        serious * 2.0 +
        moderate * 1.0 +
        area_risk * 2.0 +
        wait_capped * 0.05
    )
    score = round(score, 2)

    if score >= 6.0:
        level = "Critical"
    elif score >= 4.0:
        level = "High"
    elif score >= 2.0:
        level = "Medium"
    else:
        level = "Low"

    return score, level
