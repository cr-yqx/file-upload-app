import argparse
import io
import json
import time
import uuid
from pathlib import Path
from urllib import request as urllib_request
from http.cookiejar import CookieJar


class HttpClient:
    def __init__(self):
        self.cookie_jar = CookieJar()
        self.opener = urllib_request.build_opener(urllib_request.HTTPCookieProcessor(self.cookie_jar))

    def request_json(self, url, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib_request.Request(url=url, method=method, data=data, headers=headers)
        with self.opener.open(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text)

    def upload_file(self, url, file_name, file_bytes, content_type="application/pdf"):
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        body = io.BytesIO()
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(f"Content-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\n".encode("utf-8"))
        body.write(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.write(file_bytes)
        body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))

        req = urllib_request.Request(
            url=url,
            method="POST",
            data=body.getvalue(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with self.opener.open(req, timeout=45) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text)


def run_check(base_url: str, report_file: Path):
    client = HttpClient()
    lines = ["# Post Deploy Report", ""]

    health_status, health_payload = client.request_json(f"{base_url}/health")
    lines.append(f"- Health status: {health_status}")
    lines.append(f"- Health payload: `{json.dumps(health_payload)}`")

    room_slug = f"deploy-{uuid.uuid4().hex[:8]}"
    passcode = "deploy1234"

    status, create_payload = client.request_json(
        f"{base_url}/api/rooms",
        method="POST",
        payload={"name": "Post Deploy Check", "slug": room_slug, "passcode": passcode},
    )
    lines.append(f"- Create room status: {status}")

    status, auth_payload = client.request_json(
        f"{base_url}/api/rooms/{room_slug}/auth",
        method="POST",
        payload={"passcode": passcode},
    )
    lines.append(f"- Auth room status: {status}")

    upload_status, upload_payload = client.upload_file(
        f"{base_url}/api/rooms/{room_slug}/upload",
        "check.pdf",
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF",
    )
    lines.append(f"- Upload PDF status: {upload_status}")

    job_id = upload_payload.get("summary_job_id")
    if job_id:
        terminal = {"done", "failed"}
        current_job_status = "queued"
        started = time.time()
        while time.time() - started < 60:
            status, job_payload = client.request_json(f"{base_url}/api/rooms/{room_slug}/jobs/{job_id}")
            current_job_status = job_payload["job"]["status"]
            if current_job_status in terminal:
                break
            time.sleep(2)
        lines.append(f"- Summary job terminal status: {current_job_status}")

    status, files_payload = client.request_json(f"{base_url}/api/rooms/{room_slug}/files")
    lines.append(f"- List files status: {status}")
    lines.append(f"- File count: {len(files_payload.get('files', []))}")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return report_file


def main():
    parser = argparse.ArgumentParser(description="Run post-deploy checks and output a markdown report.")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. https://your-app.up.railway.app")
    parser.add_argument("--report-file", default="post_deploy_report.md")
    args = parser.parse_args()

    report_path = run_check(args.base_url.rstrip("/"), Path(args.report_file))
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
