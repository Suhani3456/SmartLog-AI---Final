"""
SmartLog AI — hybrid classification pipeline orchestrator.

Stages (each short-circuits the next when confident):
  1. Preprocess          strip noise, lowercase (risk: none, always runs)
  2. Regex               hand-written rules -> immediate return
  3. SBERT + LogReg      semantic match; accept at prob >= 0.70
  4. DBSCAN              cluster low-confidence logs; clustered outsiders are
                         grouped (Explorer); noise points fall through to…
  5. LLM (Claude)        last resort; any failure degrades to "Unknown"

Models load ONCE at FastAPI startup (lifespan) via load_models(); never per
request. Every function here is failure-tolerant — the pipeline must never
crash a request.
"""

import time
from typing import Optional

from config import BERT_CONFIDENCE_THRESHOLD
from pipeline.preprocess import preprocess
from pipeline import regex_classifier
from pipeline import embedder, classifier, anomaly as anomaly_stage
from pipeline import llm_fallback

_HIGH = {"Database Error", "Payment Issue", "Security Alert", "API Failure"}
_MEDIUM = {"Resource Usage", "Workflow Error", "Login Failure"}

_REMEDIATION = {
    "Database Error": "Check the DB connection pool and slow-query log; kill long transactions.",
    "API Failure": "Check the upstream service health endpoint and recent deploys.",
    "Login Failure": "Verify the auth service; check for lockouts after failed attempts.",
    "Payment Issue": "Confirm gateway status and reconcile the failed transactions.",
    "Security Alert": "Review access logs for the source IP and rotate affected credentials.",
    "Resource Usage": "Right-size the instance or recycle the worker before it hits OOM.",
    "Workflow Error": "Inspect the last failed step and re-run the job with retries reset.",
    "User Action": "No action needed; informational event.",
    "Unknown": "Forward to the on-call engineer for manual triage.",
}


def derive_severity(level: Optional[str], category: str) -> str:
    """Severity = category baseline nudged up/down by the log level."""
    if category == "Unknown":
        return "Medium"
    base = "High" if category in _HIGH else "Medium" if category in _MEDIUM else "Low"
    lv = (level or "").upper()
    if lv == "CRITICAL":
        return "Critical"
    if lv == "ERROR" and base == "Medium":
        return "High"
    if lv in ("DEBUG", "INFO") and base in ("High", "Medium") and category not in _HIGH:
        return "Low"
    return base


def load_models() -> bool:
    """
    Load every ML artifact once at startup. Returns True when the full
    pipeline is armed; False when artifacts are missing (train.py not run) —
    the app still boots and regex still works.
    """
    try:
        embedder.load()
        classifier.load()
        anomaly_stage.load()
        return True
    except RuntimeError:
        # Artifacts not trained yet: ML stages disabled, regex still serving.
        return False


def models_ready() -> bool:
    """True when all ML artifacts are loaded (reflected on /api/health)."""
    return embedder.is_loaded() and classifier.is_loaded() and anomaly_stage.is_loaded()


def classify_text(
    raw_text: str,
    level: Optional[str] = None,
    source: Optional[str] = None,
) -> dict:
    """
    Classify one raw log line through the full hybrid pipeline.

    Returns the classification contract dict (same shape as Phase 1 but with
    real stages now): category, severity, confidence, classified_by,
    cleaned_text, is_known, pipeline_trace, explanation, remediation,
    regex_rule, detection_ms.
    """
    started = time.perf_counter()
    trace: list[dict] = []

    # --- Stage 1: Preprocess --------------------------------------------------
    cleaned = preprocess(raw_text)
    trace.append({"stage": "Preprocess", "matched": True, "score": 1.0})

    def finish(result: dict) -> dict:
        result["pipeline_trace"] = trace
        result["detection_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    def unknown_result(reason: str) -> dict:
        """Graceful degrade: the LLM stage is the last deciding stage."""
        return {
            "category": "Unknown",
            "severity": "Medium",
            "confidence": 0.15,
            "classified_by": "LLM",
            "cleaned_text": cleaned,
            "is_known": False,
            "regex_rule": None,
            "explanation": reason,
            "remediation": _REMEDIATION["Unknown"],
        }

    # --- Stage 2: Regex -------------------------------------------------------
    rule_hit = regex_classifier.match(raw_text, cleaned)
    if rule_hit:
        trace.append({"stage": "Regex", "matched": True, "score": rule_hit["confidence"]})
        category = rule_hit["category"]
        severity = rule_hit["severity"]
        if (level or "").upper() in ("DEBUG", "INFO") and category == "User Action":
            severity = "Low"
        return finish({
            "category": category,
            "severity": severity,
            "confidence": rule_hit["confidence"],
            "classified_by": "Regex",
            "cleaned_text": cleaned,
            "is_known": True,
            "regex_rule": rule_hit["rule_id"],
            "explanation": (
                f"Matched the regex rule {rule_hit['rule_id']} on the key phrase "
                f"\"{rule_hit['matched_phrase']}\"."
            ),
            "remediation": _REMEDIATION.get(category, _REMEDIATION["Unknown"]),
        })
    trace.append({"stage": "Regex", "matched": False, "score": 0.0})

    # --- Stage 3: SBERT + Logistic Regression ---------------------------------
    if embedder.is_loaded() and classifier.is_loaded():
        try:
            embedding = embedder.embed([cleaned])[0]
        except Exception:  # noqa: BLE001 — embedding must never crash a request
            embedding = None

        if embedding is not None:
            try:
                ml_category, prob, _probs = classifier.predict(embedding)
            except Exception:  # noqa: BLE001
                ml_category, prob = "Unknown", 0.0
            trace.append({"stage": "BERT+LogReg", "matched": False, "score": round(prob, 4)})

            if ml_category != "Unknown" and prob >= BERT_CONFIDENCE_THRESHOLD:
                trace[-1]["matched"] = True  # this stage decided
                return finish({
                    "category": ml_category,
                    "severity": derive_severity(level, ml_category),
                    "confidence": round(prob, 4),
                    "classified_by": "BERT+LogReg",
                    "cleaned_text": cleaned,
                    "is_known": True,
                    "regex_rule": None,
                    "explanation": (
                        f"Sentence-BERT embedding matched the Logistic Regression head to "
                        f"\"{ml_category}\" with {prob:.2f} probability (≥ {BERT_CONFIDENCE_THRESHOLD:.2f} threshold)."
                    ),
                    "remediation": _REMEDIATION.get(ml_category, _REMEDIATION["Unknown"]),
                })

            # --- Stage 4: DBSCAN over low-confidence embeddings -----------------
            if anomaly_stage.is_loaded():
                try:
                    cluster_id = anomaly_stage.cluster_of(embedding)
                except Exception:  # noqa: BLE001
                    cluster_id = -1

                if cluster_id != -1:
                    trace.append({"stage": "DBSCAN", "matched": True, "score": round(prob, 4)})
                    return finish({
                        "category": "Unknown",
                        "severity": derive_severity(level, "Unknown"),
                        "confidence": round(prob, 4),
                        "classified_by": "DBSCAN",
                        "cleaned_text": cleaned,
                        "is_known": False,
                        "regex_rule": None,
                        "explanation": (
                            f"DBSCAN grouped this low-confidence log into anomaly cluster "
                            f"#{cluster_id}; flagged for the Anomaly Explorer."
                        ),
                        "remediation": _REMEDIATION["Unknown"],
                    })

                # --- Stage 5: LLM fallback -------------------------------------
                llm = llm_fallback.classify_with_llm(raw_text, cleaned)
                trace.append({"stage": "LLM", "matched": llm is not None, "score": round(prob, 4)})
                if llm is not None:
                    return finish({
                        "category": llm["category"],
                        "severity": llm["severity"],
                        "confidence": 0.60,
                        "classified_by": "LLM",
                        "cleaned_text": cleaned,
                        "is_known": True,
                        "regex_rule": None,
                        "explanation": f"LLM fallback: {llm['explanation']}",
                        "remediation": llm["remediation"] or _REMEDIATION.get(llm["category"], _REMEDIATION["Unknown"]),
                    })
                # Degrade gracefully; capped detection_ms keeps the trace honest.
                return finish(unknown_result(
                    "LLM fallback unavailable (missing key or failed call); left as Unknown."
                ))

    # Models not loaded (train.py not run): stop after Regex, degrade softly.
    trace.append({"stage": "BERT+LogReg", "matched": False, "score": 0.0})
    trace.append({"stage": "LLM", "matched": False, "score": 0.0})
    return finish(unknown_result("ML artifacts not loaded in this backend; flagged as unknown."))
