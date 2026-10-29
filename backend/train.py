"""
SmartLog AI — training script.

Run from backend/:  venv/Scripts/python train.py  (or python train.py)

What it does:
  1. Generates ~2000 labeled synthetic log lines across the 8 known
     categories with varied wording (hostnames, timestamps, IDs mixed in).
     CSVs placed in backend/data/ (LogHub style) are merged in if present.
  2. 80/20 stratified split; trains LogisticRegression on SBERT embeddings.
  3. Fits DBSCAN on the LOW-CONFIDENCE training embeddings (max prob < 0.70)
     plus a 2-component PCA for the Anomaly Explorer scatter.
  4. Prints and saves accuracy, per-class precision/recall/F1, confusion
     matrix, baseline comparison (Rule-based only vs ML only vs Hybrid,
     F1 + false-alert rate) to backend/models/metrics.json.
  5. Saves joblib artifacts to backend/models/.
"""

from __future__ import annotations

import csv
import json
import random
import time
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split

from config import (
    BERT_CONFIDENCE_THRESHOLD,
    BERT_MODEL_PATH,
    CLUSTER_PATH,
    DATA_DIR,
    METRICS_PATH,
    PCA_PATH,
)
from pipeline import embedder
from pipeline import regex_classifier
from pipeline.preprocess import preprocess

RNG = random.Random(42)

KNOWN_CATEGORIES = [
    "Database Error", "API Failure", "Login Failure", "Payment Issue",
    "Security Alert", "Resource Usage", "Workflow Error", "User Action",
]

HOSTS = {
    "CRM": ["crm-app-01", "crm-app-03", "crm-api-02"],
    "HRMS": ["hrms-web-01", "hrms-web-02", "hrms-api-01"],
    "Billing": ["billing-api-01", "billing-api-02", "billing-worker-01"],
    "Cloud/Server": ["node-02", "node-07", "edge-11", "db-primary-01"],
}

# Templates shaped as (category, level, sentences[]).
TEMPLATES: dict[str, list[tuple[str, list[str]]]] = {
    "Database Error": [
        ("ERROR", ["connection timeout after {n}s on {db}", "query timeout, statement took {n}s {db}",
                   "deadlock detected between txn {id1} and {id2}", "database is locked, retries exhausted {db}",
                   "too many connections, pool limit {n} reached", "lock wait timeout exceeded {db}",
                   "disk full on {vol}, writes failing", "ora code {id1} aborted the batch insert"]),
        ("CRITICAL", ["replication lag {n}s on {db} primary", "connection refused, listener down {db}"]),
    ],
    "API Failure": [
        ("ERROR", ["upstream {svc} timed out after {n}s, endpoint {ep}", "{svc} returned status {code} endpoint {ep}",
                   "gateway timeout calling {svc} {ep}", "bad gateway from {svc}, request {id1}",
                   "service unavailable {svc} endpoint {ep}", "failed to fetch {ep} retries {n} exhausted"]),
        ("WARN", ["degraded latency on {svc} endpoint {ep} p99 {n}ms", "circuit breaker half-open for {svc}"]),
    ],
    "Login Failure": [
        ("WARN", ["login failed user {id1} invalid credentials", "authentication failed token expired user {id1}",
                  "account locked after {n} failed attempts user {id1}", "invalid username or password attempt from {ip}",
                  "session expired for user {id1}, re-auth required"]),
        ("ERROR", ["sso callback rejected for user {id1}", "authentication backend unreachable, logins failing"]),
    ],
    "Payment Issue": [
        ("WARN", ["transaction declined card token {id1} code {code}", "refund failed order {id1} gateway mismatch",
                  "invoice {id1} settlement retry {n} failed", "chargeback received order {id1} amount disputed"]),
        ("ERROR", ["payment gateway unreachable, settlement stalled",
                   "double charge suspected order {id1} ledger mismatch"]),
    ],
    "Security Alert": [
        ("CRITICAL", ["brute force suspected from {ip}, {n} failed logins",
                      "suspicious login location mismatch user {id1} country {cc}",
                      "acl triggered for subnet {ip}", "firewall rule fired on {svc}, scan pattern detected",
                      "malformed request rejected, possible injection attempt",
                      "unauthorized access attempt on admin console"]),
        ("ERROR", ["permission denied escalation attempt user {id1}"]),
    ],
    "Resource Usage": [
        ("WARN", ["memory usage {n}% on {svc}", "cpu usage {n}% sustained on {svc}",
                  "heap usage {n}% after full garbage collection {svc}", "load average {n} on {host}",
                  "swap activity detected on {host}", "quota exceeded for {svc} storage {n}%"]),
        ("ERROR", ["out of memory killed worker {host}", "throttled by hypervisor, cpu credits low {host}"]),
    ],
    "Workflow Error": [
        ("ERROR", ["workflow {id1} job failed at step {n}", "task failed, retry limit {n} reached workflow {id1}",
                   "state machine entered invalid state from {svc}",
                   "orchestration error, step {n} skipped and downstream {svc} stalled",
                   "pipeline aborted workflow {id1}, dependency {svc} missing"]),
        ("WARN", ["workflow {id1} paused pending manual approval", "scheduled job {id1} overdue by {n}m"]),
    ],
    "User Action": [
        ("INFO", ["user logged in user {id1} ip {ip}", "user logged out user {id1}", "password changed user {id1}",
                  "profile updated user {id1}", "exported report user {id1} range last {n}d",
                  "created a ticket user {id1}", "settings updated user {id1} theme dark",
                  "performed bulk action user {id1}, records {n}"]),
    ],
}

_LEVEL_TOKEN = {"INFO": "info", "WARN": "warning", "ERROR": "error", "CRITICAL": "critical", "DEBUG": "debug"}

# Short neutral phrases appended to a few rows, mirroring real noise: in
# production, logs carry status-page chatter, batching notes etc. that are
# NOT category features. Keeps logistic regression from being trivially
# perfect and gives DBSCAN genuinely low-confidence rows to cluster.
_DISTRACTORS = [
    # Neutral chatter (belongs to no category):
    "fallback response served from cache",
    "status page incident notification attached",
    "sync batch delayed, retry scheduled",
    "notification email queued for delivery",
    "config reloaded, watchdog reset",
    "snapshot retention job completed quietly",
    "health probe roundtrip recorded per module",
    "audit trail appended by the collector",
    "scheduled maintenance window started early",
    "inventory reconciliation finished",
]
# Phrase collisions: vocabulary borrowed from OTHER categories' domains,
# which makes the ML head genuinely uncertain on some rows.
_COLLIDERS = [
    "connection pool telemetry job logged",
    "role session refresh handshake recorded",
    "gateway ping observed after gc pause",
    "settlement digest after deadlock audit",
    "firewall probe during sql background task",
    "invoice reminder from workflow scheduler",
    "memory pressure during auth handshake",
    "query plan traced by api gateway,",
]
_CCS = ["us", "de", "in", "br", "sg"]
_EPS = ["api/v2/orders", "api/v1/profile", "internal/sync", "web/checkout"]
_DBS = ["pg-main", "mysql-billing", "mongo-users"]
_VOLS = ["/data", "/var/log", "ebs-vol-3"]


def _fill(category: str, level: str) -> str:
    """Build one believable log line for the GIVEN category and level."""
    sentences = next(t for lv, t in TEMPLATES[category] if lv == level)
    template = RNG.choice(sentences)
    host = RNG.choice([h for hs in HOSTS.values() for h in hs])
    template = template.format(
        n=RNG.choice(["12", "30", "94", "87", "1024", "41", "5"]),
        id1=RNG.choice(["req", "txn", "user", "wf", "ord"]) + str(RNG.randrange(10000, 99999)),
        id2=RNG.choice(["req", "txn", "user", "wf", "ord"]) + str(RNG.randrange(10000, 99999)),
        ip=f"10.{RNG.randrange(0, 255)}.{RNG.randrange(0, 255)}.{RNG.randrange(1, 254)}",
        cc=RNG.choice(_CCS),
        code=RNG.choice(["500", "502", "503", "504", "05"]),
        db=RNG.choice(_DBS), vol=RNG.choice(_VOLS), ep="/" + RNG.choice(_EPS),
        svc=RNG.choice(["orders-api", "auth-svc", "sync-service", "pay-gateway"]),
        host=host,
    )
    now = datetime(2026, 10, RNG.randrange(1, 29), RNG.randrange(6, 23), RNG.randrange(0, 60), RNG.randrange(0, 60))
    style = RNG.random()
    if style < 0.4:
        return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {host} {template}"
    if style < 0.7:
        return f"<{now.strftime('%b')}> {now.day:02d} {now.strftime('%H:%M:%S')} {host}: {_LEVEL_TOKEN[level]}: {template}"
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}Z level={_LEVEL_TOKEN[level]} host={host} msg=\"{template}\""


def generate_dataset(n: int = 2000) -> list[dict]:
    """Synthetic labeled dataset: [{raw, level, category}]."""
    rows: list[dict] = []
    # Slight imbalance for realism (User Action and API noise heavy).
    weights = {
        "Database Error": 3, "API Failure": 3, "Login Failure": 2, "Payment Issue": 2,
        "Security Alert": 1, "Resource Usage": 2, "Workflow Error": 2, "User Action": 3,
    }
    pool = [cat for cat, w in weights.items() for _ in range(w)]
    levels_per_cat = {cat: sorted({lv for lv, _ in TEMPLATES[cat]}) for cat in TEMPLATES}
    for _ in range(n):
        category = RNG.choice(pool)
        level = RNG.choice(levels_per_cat[category])
        raw = _fill(category, level)
        if RNG.random() < 0.25:  # noise rows: ambiguous, harder for the ML head
            pool_noise = _DISTRACTORS if RNG.random() < 0.3 else _COLLIDERS
            raw = raw + ". " + RNG.choice(pool_noise)
        rows.append({"raw": raw, "level": level, "category": category})
    return rows


def load_loghub_csvs() -> list[dict]:
    """
    Load optional LogHub-style CSVs from backend/data/.
    Accepts files with a text-like column plus either a 'category'/'label'
    column or a known source->category file name mapping; unknown files skip.
    """
    loaded: list[dict] = []
    if not DATA_DIR.exists():
        return loaded
    name_map = {
        "hadoop": "Resource Usage", "linux": "Security Alert", "apache": "API Failure",
        "ssh": "Security Alert", "oracle": "Database Error", "prograder": "Workflow Error",
        "bgl": "Resource Usage",
    }
    text_col = next((c for c in ["text", "message", "log", "raw", "content"]), None)
    for path in sorted(DATA_DIR.glob("*.csv")):
        mapped = next((v for k, v in name_map.items() if k in path.name.lower()), None)
        with open(path, encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                continue
            text_idx = next((i for i, c in enumerate(header) if c.lower() == text_col), None)
            cat_idx = next((i for i, c in enumerate(header) if c.lower() in ("category", "label")), None)
            if text_idx is None:
                text_idx = 0  # fall back to first column for headerless LogHub files
                cat_idx = None
            for row in reader:
                if len(row) <= text_idx or not row[text_idx].strip():
                    continue
                category = None
                if cat_idx is not None and len(row) > cat_idx and row[cat_idx].strip() in KNOWN_CATEGORIES:
                    category = row[cat_idx].strip()
                if category is None:
                    category = mapped
                if category is None:
                    continue
                loaded.append({"raw": row[text_idx], "category": category, "level": "ERROR"})
    return loaded


# --- Baseline metric helpers ---------------------------------------------------

def f1_and_false_alerts(y_true: list[str], y_pred: list[str]) -> tuple[float, float]:
    """
    (macro F1, false-alert rate).

    Predicting "Unknown" counts as abstaining (no alert raised), so the
    false-alert rate is the fraction of *raised* alerts that were wrong.
    """
    labels = sorted(set(y_true) | {p for p in y_pred if p != "Unknown"})
    f1 = f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    raised = [i for i, p in enumerate(y_pred) if p != "Unknown"]
    if not raised:
        return float(f1), 0.0
    wrong = sum(1 for i in raised if y_pred[i] != y_true[i])
    return float(f1), wrong / len(raised)


def nearest_core_cluster(model: DBSCAN, embeddings_arr, labels_arr, emb):
    """Cluster id (-1 = noise) via nearest core sample, mirroring runtime."""
    non_noise = np.flatnonzero(labels_arr != -1)
    if non_noise.size == 0:
        return -1
    core_emb = embeddings_arr[non_noise]
    core_lbl = labels_arr[non_noise]
    dists = np.linalg.norm(core_emb - emb, axis=1)
    k = int(dists.argmin())
    return int(core_lbl[k]) if float(dists[k]) <= model.eps else -1


def main() -> None:
    started = time.perf_counter()
    print("== SmartLog AI training ==")

    # 1. Dataset ----------------------------------------------------------------
    data = generate_dataset(2000)
    external = load_loghub_csvs()
    if external:
        print(f"Merged {len(external)} rows from backend/data/ CSVs.")
    data.extend(external)
    counts = {c: sum(1 for r in data if r["category"] == c) for c in KNOWN_CATEGORIES}
    print(f"Dataset: {len(data)} rows — " + ", ".join(f"{c}: {counts[c]}" for c in KNOWN_CATEGORIES))

    texts = [row["raw"] for row in data]
    categories_all = [row["category"] for row in data]

    print("Preprocessing…")
    cleaned = [preprocess(t) for t in texts]

    # 2. Split -------------------------------------------------------------------
    train_idx, test_idx = train_test_split(
        list(range(len(data))), test_size=0.20, stratify=categories_all, random_state=42
    )

    print("Embedding with all-MiniLM-L6-v2 (first run downloads the model)…")
    embedder.load()  # SBERT loads once here; the API reuses it at startup
    embeddings = embedder.embed(cleaned)

    # 3. Train Logistic Regression ------------------------------------------------
    clf = LogisticRegression(max_iter=2000, C=4.0)
    y_train = [categories_all[i] for i in train_idx]
    clf.fit(embeddings[train_idx], y_train)

    proba_test = clf.predict_proba(embeddings[test_idx])
    pred_test = clf.classes_[proba_test.argmax(axis=1)]
    y_true = [categories_all[i] for i in test_idx]
    accuracy = accuracy_score(y_true, pred_test)
    print(f"LogReg accuracy on test split: {accuracy * 100:.1f}%")
    print(f"LogReg macro F1 on test split: {f1_score(y_true, pred_test, average='macro', zero_division=0) * 100:.1f}%")

    # 4. DBSCAN (+PCA) on LOW-CONFIDENCE training rows -----------------------------
    conf_train = clf.predict_proba(embeddings[train_idx]).max(axis=1)
    low_local = np.flatnonzero(conf_train < BERT_CONFIDENCE_THRESHOLD)
    low_emb = embeddings[train_idx][low_local]
    if len(low_emb) < 20:  # DBSCAN needs some mass; widen to most-uncertain rows
        low_local = np.argsort(conf_train)[: max(20, len(conf_train) // 20)]
        low_emb = embeddings[train_idx][low_local]
    dbscan = DBSCAN(eps=0.35, min_samples=3, metric="cosine")
    dbscan_labels = dbscan.fit_predict(low_emb)
    pca = PCA(n_components=2, random_state=42).fit(low_emb)
    n_clusters = len(set(dbscan_labels)) - (1 if -1 in set(dbscan_labels) else 0)
    n_noise = int(np.sum(np.asarray(dbscan_labels) == -1))
    print(f"DBSCAN on {len(low_emb)} low-confidence embeddings: "
          f"{n_clusters} clusters, {n_noise} noise points")

    # 5. Simulate the three baselines on the test split -----------------------------
    y_rule, y_mlonly, y_hybrid = [], [], []
    by_classifier = {"Regex": 0, "BERT+LogReg": 0, "DBSCAN": 0, "LLM": 0}
    for j, i_test in enumerate(test_idx):
        row = data[i_test]
        emb_j = embeddings[i_test]
        prob_j = float(proba_test[j].max())
        ml_pred = pred_test[j]

        y_mlonly.append(ml_pred)  # ML-only always answers, no threshold

        rule = regex_classifier.match(row["raw"], cleaned[i_test])
        if rule:  # Rule-based fires; hybrid agrees and short-circuits
            y_rule.append(rule["category"])
            y_hybrid.append(rule["category"])
            by_classifier["Regex"] += 1
            continue
        y_rule.append("Unknown")

        if ml_pred != "Unknown" and prob_j >= BERT_CONFIDENCE_THRESHOLD:
            y_hybrid.append(ml_pred)
            by_classifier["BERT+LogReg"] += 1
        else:
            cluster_id = nearest_core_cluster(dbscan, low_emb, dbscan_labels, emb_j)
            if cluster_id != -1:
                y_hybrid.append("Unknown")  # clustered outsider: unknown but grouped
                by_classifier["DBSCAN"] += 1
            else:
                y_hybrid.append("Unknown")  # would call Claude here; abstains without key
                by_classifier["LLM"] += 1

    rule_f1, rule_fa = f1_and_false_alerts(y_true, y_rule)
    ml_f1, ml_fa = f1_and_false_alerts(y_true, y_mlonly)
    hyb_f1, hyb_fa = f1_and_false_alerts(y_true, y_hybrid)

    # 6. Per-class + confusion matrix from the HYBRID decisions ----------------------
    labels_present = sorted({c for c in y_true} | {y for y in y_hybrid if y != "Unknown"})
    prec, rec, f1s, support = precision_recall_fscore_support(
        y_true, y_hybrid, labels=labels_present, zero_division=0
    )
    cm = confusion_matrix(y_true, y_hybrid, labels=labels_present)
    total = sum(by_classifier.values()) or 1

    metrics = {
        "accuracy": round(float(accuracy), 4),
        "f1_macro": round(hyb_f1, 4),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": "all-MiniLM-L6-v2",
        "bert_threshold": BERT_CONFIDENCE_THRESHOLD,
        "per_class": [
            {"category": labels_present[i], "precision": round(float(prec[i]), 4),
             "recall": round(float(rec[i]), 4), "f1": round(float(f1s[i]), 4),
             "support": int(support[i])}
            for i in range(len(labels_present))
        ],
        "confusion_matrix": {"labels": labels_present, "matrix": cm.tolist()},
        "dbscan": {"eps": dbscan.eps, "min_samples": dbscan.min_samples,
                   "n_clusters": n_clusters, "n_noise": n_noise,
                   "low_confidence_rows": int(len(low_emb))},
        "baseline_comparison": [
            {"approach": "Rule-based only", "f1": round(rule_f1, 4), "false_alert_rate": round(rule_fa, 4)},
            {"approach": "ML only", "f1": round(ml_f1, 4), "false_alert_rate": round(ml_fa, 4)},
            {"approach": "Hybrid", "f1": round(hyb_f1, 4), "false_alert_rate": round(hyb_fa, 4)},
        ],
        "classifier_usage": [
            {"classified_by": who, "share": round(count / total, 4)}
            for who, count in sorted(by_classifier.items(), key=lambda kv: -kv[1])
        ],
    }

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_PATH, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    # 7. Joblib artifacts ----------------------------------------------------------
    joblib.dump({"model": clf, "labels": sorted(set(categories_all)),
                 "trained_at": metrics["trained_at"], "threshold": BERT_CONFIDENCE_THRESHOLD},
                BERT_MODEL_PATH)
    joblib.dump({"model": dbscan, "train_embeddings": low_emb, "labels": dbscan_labels}, CLUSTER_PATH)
    joblib.dump(pca, PCA_PATH)

    # 8. Report ----------------------------------------------------------------------
    print("\n--- Test metrics ---")
    print(f"Accuracy (LogReg head): {accuracy * 100:.1f}%")
    print(f"Hybrid macro F1:        {hyb_f1 * 100:.1f}%")
    print("\nPer-class (hybrid decisions, Unknown included):")
    for i, category in enumerate(labels_present):
        print(f"  {category:<16} P {prec[i]:.2f}  R {rec[i]:.2f}  F1 {f1s[i]:.2f}  n {support[i]}")
    print("\nBaselines:")
    print("  Rule-based only : F1 %.3f  false-alert %.3f" % (rule_f1, rule_fa))
    print("  ML only         : F1 %.3f  false-alert %.3f" % (ml_f1, ml_fa))
    print("  Hybrid          : F1 %.3f  false-alert %.3f" % (hyb_f1, hyb_fa))
    print("\nClassifier usage:", metrics["classifier_usage"])
    print(f"\nSaved: {METRICS_PATH}\nSaved: {BERT_MODEL_PATH}")
    print(f"Saved: {CLUSTER_PATH}\nSaved: {PCA_PATH}")
    print(f"\nDone in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
