import os
import io
import json
from typing import Optional, Tuple

import requests
from flask import Flask, jsonify, request, send_file


APP = Flask(__name__)
# Expose lowercase 'app' for WSGI servers like gunicorn (server:app)
app = APP

MATHPIX_BASE_URL = "https://api.mathpix.com/v3/pdf"


def _get_mathpix_headers() -> dict:
	app_id = os.getenv("MATHPIX_APP_ID")
	app_key = os.getenv("MATHPIX_APP_KEY")
	return {
		"app_id": app_id or "",
		"app_key": app_key or "",
	}


def _validate_env() -> Optional[str]:
	headers = _get_mathpix_headers()
	missing = [k for k, v in headers.items() if not v]
	if missing:
		return (
			"Missing required environment variables: "
			+ ", ".join(
				["MATHPIX_APP_ID" if k == "app_id" else "MATHPIX_APP_KEY" for k in missing]
			)
		)
	return None


def mathpix_start_job(file_bytes: bytes, filename: str, options: Optional[dict] = None) -> Tuple[int, dict]:
	"""Submit a PDF to Mathpix and return (status_code, response_json)."""
	options = options or {
		"conversion_formats": {"md": True, "tex.zip": True},
		"math_inline_delimiters": ["$", "$"],
		"rm_spaces": True,
	}

	headers = _get_mathpix_headers()
	try:
		resp = requests.post(
			MATHPIX_BASE_URL,
			headers=headers,
			data={"options_json": json.dumps(options)},
			files={"file": (filename, file_bytes, "application/pdf")},
			timeout=60,
		)
	except requests.RequestException as e:
		return 502, {"error": f"Upstream request failed: {e.__class__.__name__}: {e}"}
    
	# Ensure JSON payload even on non-200
	try:
		payload = resp.json()
	except ValueError:
		payload = {"error": "Invalid response from Mathpix (non-JSON)", "text": resp.text}
	return resp.status_code, payload


def mathpix_status(pdf_id: str) -> Tuple[int, dict]:
	headers = _get_mathpix_headers()
	try:
		resp = requests.get(f"{MATHPIX_BASE_URL}/{pdf_id}", headers=headers, timeout=30)
	except requests.RequestException as e:
		return 502, {"error": f"Upstream request failed: {e.__class__.__name__}: {e}"}
	try:
		payload = resp.json()
	except ValueError:
		payload = {"error": "Invalid response from Mathpix (non-JSON)", "text": resp.text}
	return resp.status_code, payload


def mathpix_download_md(pdf_id: str) -> Tuple[int, Optional[bytes], Optional[str]]:
	headers = _get_mathpix_headers()
	url = f"{MATHPIX_BASE_URL}/{pdf_id}.md"
	try:
		resp = requests.get(url, headers=headers, timeout=60)
	except requests.RequestException as e:
		return 502, None, f"Upstream request failed: {e.__class__.__name__}: {e}"
	if resp.status_code != 200:
		# Try to decode JSON error if present
		try:
			err = resp.json()
		except ValueError:
			err = {"error": resp.text}
		return resp.status_code, None, json.dumps(err)
	return 200, resp.content, None


@APP.get("/health")
def health():
	missing = _validate_env()
	return jsonify({"status": "ok", "env_ok": missing is None, "missing": missing}), 200


@APP.post("/process")
def process_pdf():
	# Validate env
	missing = _validate_env()
	if missing:
		return jsonify({"error": missing}), 500

	if "file" not in request.files:
		return jsonify({"error": "No file part provided. Use multipart/form-data with field 'file'."}), 400

	file = request.files["file"]
	if not file or not file.filename or file.filename == "":
		return jsonify({"error": "Empty filename."}), 400

	if not file.filename.lower().endswith(".pdf"):
		return jsonify({"error": "Only PDF files are supported."}), 400

	# Optional custom options via JSON field 'options'
	opts = None
	if "options" in request.form:
		try:
			opts = json.loads(request.form["options"]) if request.form["options"] else None
		except json.JSONDecodeError:
			return jsonify({"error": "Invalid JSON in 'options' field."}), 400

	file_bytes = file.read()
	status_code, payload = mathpix_start_job(file_bytes, file.filename, opts)
	if status_code >= 400:
		return jsonify(payload), status_code

	pdf_id = payload.get("pdf_id")
	if not pdf_id:
		return jsonify({"error": "Missing pdf_id in Mathpix response.", "upstream": payload}), 502

	base_url = request.url_root.rstrip("/")
	return (
		jsonify(
			{
				"message": "Upload successful. Poll status via /status/<pdf_id>.",
				"pdf_id": pdf_id,
				"status_url": f"{base_url}/status/{pdf_id}",
				"download_url": f"{base_url}/download/{pdf_id}.md",
			}
		),
		202,
	)


@APP.get("/status/<pdf_id>")
def status(pdf_id: str):
	missing = _validate_env()
	if missing:
		return jsonify({"error": missing}), 500
	status_code, payload = mathpix_status(pdf_id)
	return jsonify(payload), status_code


@APP.get("/download/<pdf_id>.md")
def download_markdown(pdf_id: str):
	missing = _validate_env()
	if missing:
		return jsonify({"error": missing}), 500
	status_code, content, err = mathpix_download_md(pdf_id)
	if status_code != 200 or content is None:
		# Surface upstream error
		try:
			err_json = json.loads(err) if err and err.startswith("{") else {"error": err}
		except Exception:
			err_json = {"error": err}
		return jsonify(err_json), status_code

	# Allow optional filename via ?filename=...
	filename = request.args.get("filename", f"{pdf_id}.md")
	return send_file(
		io.BytesIO(content),
		as_attachment=True,
		download_name=filename,
		mimetype="text/markdown; charset=utf-8",
		max_age=0,
	)


if __name__ == "__main__":
	# Enable local development server
	port = int(os.getenv("PORT", "5000"))
	APP.run(host="0.0.0.0", port=port, debug=True)
