import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urllib_request

from sqlalchemy import create_engine, text


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def build_report(database_url: str) -> str:
    normalized_url = normalize_database_url(database_url)
    engine = create_engine(normalized_url)

    since = datetime.now(timezone.utc) - timedelta(days=1)

    with engine.connect() as conn:
        total_files = conn.execute(text("SELECT COUNT(*) FROM files WHERE created_at >= :since"), {"since": since}).scalar() or 0
        summary_done = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE created_at >= :since AND summary_status = 'done'"),
            {"since": since},
        ).scalar() or 0
        summary_failed = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE created_at >= :since AND summary_status = 'failed'"),
            {"since": since},
        ).scalar() or 0

        top_failures_rows = conn.execute(
            text(
                """
                SELECT COALESCE(summary_error, 'Unknown') AS reason, COUNT(*) AS cnt
                FROM files
                WHERE created_at >= :since AND summary_status = 'failed'
                GROUP BY COALESCE(summary_error, 'Unknown')
                ORDER BY cnt DESC
                LIMIT 3
                """
            ),
            {"since": since},
        ).fetchall()

    success_rate = 0.0
    if total_files > 0:
        success_rate = (summary_done / total_files) * 100

    lines = [
        "# Daily AI Room Report",
        "",
        f"- Time window start (UTC): {since.isoformat()}",
        f"- New files: {total_files}",
        f"- Summary done: {summary_done}",
        f"- Summary failed: {summary_failed}",
        f"- Summary success rate: {success_rate:.2f}%",
        "",
        "## Top failure reasons",
    ]

    if not top_failures_rows:
        lines.append("- None")
    else:
        for row in top_failures_rows:
            lines.append(f"- {row.reason}: {row.cnt}")

    return "\n".join(lines)


def send_webhook(webhook_url: str, report_text: str) -> None:
    payload = json.dumps({"text": report_text}).encode("utf-8")
    req = urllib_request.Request(
        url=webhook_url,
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib_request.urlopen(req, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"Webhook request failed: HTTP {response.status}")


def main():
    parser = argparse.ArgumentParser(description="Generate daily metrics for AI room uploads and summaries.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", default="daily_report.md")
    parser.add_argument("--webhook-url", default="")
    args = parser.parse_args()

    report = build_report(args.database_url)
    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")
    print(f"Report written to {output_path}")

    if args.webhook_url:
        send_webhook(args.webhook_url, report)
        print("Webhook delivered.")


if __name__ == "__main__":
    main()
