"""Zappa entrypoint — surfaces import errors instead of opaque NoneType WSGI failures."""
import os
import traceback

try:
    from app import app as application
except Exception:
    from flask import Flask, jsonify

    application = Flask(__name__)
    _BOOT_ERROR = traceback.format_exc()

    @application.route("/health", methods=["GET"])
    @application.route("/<path:_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def boot_error(_path=""):
        return jsonify({
            "status": "boot_failed",
            "error": _BOOT_ERROR,
            "env_present": sorted(k for k in os.environ if k.startswith(("NEO4J", "SUPABASE", "ENCRYPTION", "GROQ", "REDIS", "ALLOWED"))),
        }), 500
