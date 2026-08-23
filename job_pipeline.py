import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs
from dotenv import load_dotenv


load_dotenv()


DEFAULT_EXPERIENCE_PATTERN = (
    r"(?:0\s*[-to]\s*1|0\s*[-to]\s*2|1\s*[-to]\s*2|1\s*[-to]\s*3|"
    r"1\+?\s*years?|minimum\s+1|at\s+least\s+1|one\s+year)"
)

ROLE_PRIORITIES = {
    "gtm engineer": 100,
    "revenue operations": 95,
    "revops": 95,
    "ai automation": 90,
    "rev ops strategy": 85,
    "demand generation": 75,
}


def env_list(name, default):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def text_value(row, column):
    value = row.get(column, "")
    return "" if pd.isna(value) else str(value).strip()


def matches_experience(row, pattern):
    level = text_value(row, "job_level").lower()
    description = text_value(row, "description")
    return level in {"entry level", "associate", "internship"} or bool(
        re.search(pattern, description, flags=re.IGNORECASE)
    )


def role_match(title):
    title = title.lower()
    matches = [
        (score, label)
        for label, score in ROLE_PRIORITIES.items()
        if label in title
    ]
    return max(matches, default=(0, "Other"))


def salary_value(row):
    salary = " ".join(
        text_value(row, column)
        for column in ("min_amount", "max_amount", "interval", "currency")
    )
    amounts = [float(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", salary)]
    if not amounts:
        return None
    amount = max(amounts)
    interval = text_value(row, "interval").lower()
    if interval.startswith("month"):
        amount *= 12
    return amount


def collect_jobs():
    frames = []
    for search_term in env_list(
        "JOB_SEARCH_TERMS",
        "GTM Engineer,Revenue Operations,AI Automation Engineer,RevOps Strategy,Demand Generation",
    ):
        for location in env_list("JOB_LOCATIONS", "India,Remote"):
            frames.append(
                scrape_jobs(
                    site_name=env_list("JOB_SITES", "indeed,linkedin"),
                    search_term=search_term,
                    location=location,
                    results_wanted=int(os.getenv("JOB_RESULTS_WANTED", "20")),
                    hours_old=int(os.getenv("JOB_HOURS_OLD", "168")),
                    country_indeed=os.getenv("JOB_COUNTRY_INDEED", "India"),
                )
            )

    jobs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if jobs.empty:
        return jobs

    experience_pattern = os.getenv(
        "JOB_EXPERIENCE_PATTERN", DEFAULT_EXPERIENCE_PATTERN
    )
    jobs = jobs.copy()
    jobs["job_url"] = jobs.apply(
        lambda row: text_value(row, "job_url") or text_value(row, "job_url_direct"),
        axis=1,
    )
    jobs = jobs[jobs["job_url"].ne("")].drop_duplicates(subset=["job_url"])
    jobs = jobs[
        jobs.apply(lambda row: matches_experience(row, experience_pattern), axis=1)
    ]

    minimum_salary = float(os.getenv("JOB_MIN_ANNUAL_INR", "420000"))
    jobs["salary_annual_inr"] = jobs.apply(salary_value, axis=1)
    jobs = jobs[
        jobs["salary_annual_inr"].isna()
        | jobs["salary_annual_inr"].ge(minimum_salary)
    ]

    run_time = datetime.now(timezone.utc).isoformat()
    output = []
    for _, row in jobs.iterrows():
        priority, profile = role_match(text_value(row, "title"))
        output.append(
            {
                "job_url": text_value(row, "job_url"),
                "title": text_value(row, "title"),
                "company": text_value(row, "company"),
                "location": text_value(row, "location"),
                "site": text_value(row, "site"),
                "job_level": text_value(row, "job_level"),
                "date_posted": text_value(row, "date_posted"),
                "description": text_value(row, "description"),
                "target_profile": profile,
                "priority_score": priority,
                "salary_annual_inr": text_value(row, "salary_annual_inr"),
                "search_run_at": run_time,
                "status": "New",
                "follow_up_date": "",
                "applied_at": "",
                "notes": "",
            }
        )
    return output


def main():
    result = collect_jobs()
    if isinstance(result, pd.DataFrame):
        rows = result.to_dict(orient="records")
    else:
        rows = result

    output_path = Path(os.getenv("JOB_OUTPUT_JSON", "job_queue.json"))
    output_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"count": len(rows), "output": str(output_path.resolve()), "jobs": rows}))


if __name__ == "__main__":
    main()
