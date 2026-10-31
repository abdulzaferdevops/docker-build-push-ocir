"""Inventory API - Lab 2 (jenkins-flask-api-pipeline).

A small read-only JSON API served by gunicorn behind nginx. The catalogue is
shipped with each release in data/items.json; the pipeline writes a RELEASE
file next to this module so /health reports exactly which build is live.
"""
import json
from pathlib import Path

from flask import Flask, abort, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "items.json"
RELEASE_FILE = BASE_DIR / "RELEASE"


def load_items(path=DATA_FILE):
    """Load the catalogue and index it by item id."""
    with open(path, encoding="utf-8") as handle:
        items = json.load(handle)
    return {item["id"]: item for item in items}


def read_release(path=RELEASE_FILE):
    """Read release metadata written by the pipeline (key=value lines)."""
    info = {"release": "dev", "commit": "unknown", "built": "unknown"}
    path = Path(path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key in info:
                info[key] = value.strip()
    return info


def create_app(items=None, release=None):
    app = Flask(__name__)
    app.config["ITEMS"] = items if items is not None else load_items()
    app.config["RELEASE"] = release if release is not None else read_release()

    @app.get("/")
    def index():
        return jsonify(
            service="inventory-api",
            release=app.config["RELEASE"]["release"],
            endpoints=["/health", "/api/items", "/api/items/<id>"],
        )

    @app.get("/health")
    def health():
        return jsonify(status="ok", **app.config["RELEASE"])

    @app.get("/api/items")
    def list_items():
        result = list(app.config["ITEMS"].values())

        category = request.args.get("category")
        if category:
            result = [i for i in result if i["category"].lower() == category.lower()]

        low_stock = request.args.get("low_stock")
        if low_stock is not None:
            try:
                threshold = int(low_stock)
            except ValueError:
                abort(400, description="low_stock must be an integer")
            result = [i for i in result if i["quantity"] <= threshold]

        result.sort(key=lambda i: i["id"])
        return jsonify(count=len(result), items=result)

    @app.get("/api/items/<int:item_id>")
    def get_item(item_id):
        item = app.config["ITEMS"].get(item_id)
        if item is None:
            abort(404, description=f"item {item_id} not found")
        return jsonify(item)

    @app.errorhandler(400)
    @app.errorhandler(404)
    def handle_error(err):
        return jsonify(error=err.name, message=err.description), err.code

    return app


app = create_app()
