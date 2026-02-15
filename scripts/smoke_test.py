import argparse
import io
import json
import time
import uuid
from http.cookiejar import CookieJar
from urllib import request as urllib_request


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
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)

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
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload


def run_smoke(base_url: str):
    client = HttpClient()
    room_slug = f"smoke-{uuid.uuid4().hex[:8]}"
    passcode = "smoke1234"

    print("[1/5] Creating room")
    status, payload = client.request_json(
        f"{base_url}/api/rooms",
        method="POST",
        payload={"name": "Smoke Room", "slug": room_slug, "passcode": passcode},
    )
    assert status == 200 and payload.get("success"), payload

    print("[2/5] Auth room")
    status, payload = client.request_json(
        f"{base_url}/api/rooms/{room_slug}/auth",
        method="POST",
        payload={"passcode": passcode},
    )
    assert status == 200 and payload.get("success"), payload

    print("[3/5] Upload pdf")
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    status, payload = client.upload_file(
        f"{base_url}/api/rooms/{room_slug}/upload",
        "smoke.pdf",
        pdf_bytes,
    )
    assert status == 200 and payload.get("success"), payload

    job_id = payload.get("summary_job_id")

    print("[4/5] List files")
    status, payload = client.request_json(f"{base_url}/api/rooms/{room_slug}/files")
    assert status == 200 and payload.get("success"), payload
    assert len(payload.get("files", [])) == 1, payload

    if job_id:
        print("[5/5] Polling summary job")
        terminal = {"done", "failed"}
        started = time.time()
        while time.time() - started < 60:
            status, payload = client.request_json(f"{base_url}/api/rooms/{room_slug}/jobs/{job_id}")
            assert status == 200 and payload.get("success"), payload
            current_status = payload["job"]["status"]
            if current_status in terminal:
                print(f"Job finished with status: {current_status}")
                break
            time.sleep(2)

    print("Smoke test completed.")


def main():
    parser = argparse.ArgumentParser(description="Run API smoke tests for the AI room app.")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. https://your-app.up.railway.app")
    args = parser.parse_args()

    run_smoke(args.base_url.rstrip("/"))


if __name__ == "__main__":
    main()
