from __future__ import annotations

from app.models.schemas import CompareResult, Issue, ReviewResult


def compare_reviews(original: ReviewResult, revised: ReviewResult) -> CompareResult:
    original_by_title = {item.title: item for item in original.issues}
    revised_by_title = {item.title: item for item in revised.issues}

    fixed_titles = sorted(set(original_by_title) - set(revised_by_title))
    remaining_titles = sorted(set(original_by_title) & set(revised_by_title))
    new_titles = sorted(set(revised_by_title) - set(original_by_title))

    fixed_issues = [original_by_title[title] for title in fixed_titles]
    remaining_issues = [revised_by_title[title] for title in remaining_titles]
    new_issues = [revised_by_title[title] for title in new_titles]
    score_delta = round(revised.total_score - original.total_score, 1)

    return CompareResult(
        original=original,
        revised=revised,
        score_delta=score_delta,
        pass_probability_changed=original.pass_probability != revised.pass_probability,
        fixed_issues=fixed_issues,
        remaining_issues=remaining_issues,
        new_issues=new_issues,
        summary=_build_summary(score_delta, fixed_issues, remaining_issues, new_issues),
    )


def _build_summary(
    score_delta: float,
    fixed_issues: list[Issue],
    remaining_issues: list[Issue],
    new_issues: list[Issue],
) -> str:
    if score_delta > 0:
        trend = f"修改后总分提升 {score_delta} 分"
    elif score_delta < 0:
        trend = f"修改后总分下降 {abs(score_delta)} 分"
    else:
        trend = "修改前后总分未发生变化"

    return (
        f"{trend}；已修复 {len(fixed_issues)} 个问题，"
        f"仍有 {len(remaining_issues)} 个问题未解决，新增 {len(new_issues)} 个问题。"
    )
