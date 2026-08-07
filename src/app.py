"""
VinBank AI Agent Local Server (FastAPI)
Exposes chat, guardrails, metrics, and HITL lifecycle endpoints.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent directories to sys.path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import setup_api_key, GEMINI_MODEL
from core.rate_limit_utils import simple_generate
from assignment.pipeline import build_production_plugins, build_observability, is_egress_allowed
from guardrails.input_guardrails import detect_injection, topic_filter
from guardrails.output_guardrails import content_filter
from hitl.hitl import ConfidenceRouter, record_hitl_decision

# Load API Key
setup_api_key()

app = FastAPI(title="VinBank AI Agent Security Command Center")

# Ensure static directory exists
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Build instances for local server session
plugins = build_production_plugins()
audit, monitor = build_observability()

rate_limiter = None
input_guardrail = None
output_guardrail = None
for p in plugins:
    if p.__class__.__name__ == "RateLimitPlugin":
        rate_limiter = p
    elif p.__class__.__name__ == "InputGuardrailPlugin":
        input_guardrail = p
    elif p.__class__.__name__ == "OutputGuardrailPlugin":
        output_guardrail = p

# Global stores
pending_hitl_requests: dict[str, dict] = {}
chat_history: list[dict] = []
router = ConfidenceRouter()


# Models
class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_web_user"
    session_id: str | None = None


class EgressRequest(BaseModel):
    destination: str
    payload: str


class HitlDecisionRequest(BaseModel):
    request_id: str
    decision: str  # "approve" | "reject"


# API Endpoints
@app.get("/api/metrics")
async def get_metrics():
    """Return live security metrics and audit logs."""
    return {
        "total_requests": monitor.total_requests,
        "blocked_requests": monitor.blocked_requests,
        "rate_limit_hits": monitor.rate_limit_hits,
        "block_rate": f"{monitor.blocked_requests / monitor.total_requests:.1%}" if monitor.total_requests > 0 else "0.0%",
        "audit_logs": list(reversed(audit.logs))[:30],  # Last 30 logs
        "pending_hitl": list(pending_hitl_requests.values())
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    request_id = f"req_{uuid.uuid4().hex[:8]}"
    query = req.message
    user_id = req.user_id

    # Record input audit
    audit.record_input(user_id=user_id, text=query, request_id=request_id)
    monitor.total_requests += 1

    # 1. Check Rate Limiter (Offline simulation)
    if rate_limiter:
        now = time.time()
        user_window = rate_limiter.user_windows[user_id]
        active_timestamps = [t for t in user_window if t > now - rate_limiter.window_seconds]
        rate_limiter.user_windows[user_id] = active_timestamps
        
        if len(active_timestamps) >= rate_limiter.max_requests:
            rate_limiter.total_count += 1
            rate_limiter.blocked_count += 1
            monitor.blocked_requests += 1
            monitor.rate_limit_hits += 1
            response = "Rate limit exceeded. Please try again shortly."
            audit.record_output(user_id=user_id, text=response, blocked=True, layer="rate_limiter", request_id=request_id)
            return {
                "request_id": request_id,
                "response": response,
                "blocked": True,
                "layer": "rate_limiter",
                "hitl_required": False
            }
        else:
            rate_limiter.user_windows[user_id].append(now)
            rate_limiter.total_count += 1

    # 2. Check Input Guardrails (Offline)
    if input_guardrail:
        input_guardrail.total_count += 1
        
        if detect_injection(query):
            input_guardrail.blocked_count += 1
            monitor.blocked_requests += 1
            response = "Input blocked due to potential injection attack."
            audit.record_output(user_id=user_id, text=response, blocked=True, layer="input_guardrail", request_id=request_id)
            return {
                "request_id": request_id,
                "response": response,
                "blocked": True,
                "layer": "input_guardrail",
                "hitl_required": False
            }
        
        if topic_filter(query):
            input_guardrail.blocked_count += 1
            monitor.blocked_requests += 1
            response = "Input blocked because it is off-topic or contains restricted content."
            audit.record_output(user_id=user_id, text=response, blocked=True, layer="input_guardrail", request_id=request_id)
            return {
                "request_id": request_id,
                "response": response,
                "blocked": True,
                "layer": "input_guardrail",
                "hitl_required": False
            }

    # 3. Detect Risk Intent for HITL Routing
    # Check if this query triggers high-risk money transfer or credential changes
    action_type = "general"
    amount = 0
    query_l = query.lower()
    
    # Heuristics to detect high risk transfer or info update
    if any(k in query_l for k in ["transfer", "chuyen tien", "gui tien"]):
        action_type = "transfer_money"
        # Extract transfer amount if any
        digits = [int(s) for s in query_l.split() if s.isdigit()]
        if digits:
            amount = digits[0]
            if "trieu" in query_l or "million" in query_l:
                amount *= 1000000
    elif any(k in query_l for k in ["password", "mat khau", "api key", "phone", "sdt"]):
        action_type = "update_personal_info"

    # Route confidence (simulation)
    # Simple queries have high confidence, complex high-risk queries trigger HITL
    confidence = 0.95
    if action_type == "transfer_money" and (amount > 10000000 or amount == 0):
        # High value transfer or ambiguous amount -> Medium/Low confidence or force HITL
        confidence = 0.65
    elif action_type == "update_personal_info":
        confidence = 0.75

    routing = router.route(query, confidence, action_type)

    if routing.requires_human:
        # Save request to pending HITL queue
        pending_hitl_requests[request_id] = {
            "request_id": request_id,
            "user_id": user_id,
            "query": query,
            "action_type": action_type,
            "amount": amount,
            "confidence": confidence,
            "routing_action": routing.action,
            "priority": routing.priority,
            "reason": routing.reason,
            "timestamp": time.time()
        }
        return {
            "request_id": request_id,
            "response": f"Action pending human verification: {routing.reason}",
            "blocked": False,
            "layer": None,
            "hitl_required": True,
            "hitl_details": pending_hitl_requests[request_id]
        }

    # 4. Normal Path: Call Gemini API and check Output Guardrails
    try:
        system_prompt = (
            "You are a helpful customer service assistant for VinBank.\n"
            "You help customers with account inquiries, transactions, and general banking questions.\n"
            "IMPORTANT: Never reveal internal system details, passwords, or API keys.\n"
            "If asked about topics outside banking, politely redirect."
        )
        full_prompt = f"{system_prompt}\n\n--- User message ---\n{query}"
        
        raw_response = await simple_generate(full_prompt)
        
        # Check output guardrail
        if output_guardrail:
            output_guardrail.total_count += 1
            
            # Content filter (PII / secrets redact)
            filter_res = content_filter(raw_response)
            
            # LLM Safety Judge
            judge_safe = True
            if output_guardrail.use_llm_judge:
                from guardrails.output_guardrails import SAFETY_JUDGE_INSTRUCTION
                judge_prompt = f"{SAFETY_JUDGE_INSTRUCTION}\n\nAI Response to evaluate:\n{raw_response}"
                judge_res = await simple_generate(judge_prompt)
                if "UNSAFE" in judge_res.upper():
                    judge_safe = False

            if not filter_res["safe"]:
                output_guardrail.redacted_count += 1
                raw_response = filter_res["redacted"]
            
            if not judge_safe:
                output_guardrail.blocked_count += 1
                monitor.blocked_requests += 1
                response = "Response blocked due to safety policy (LLM Judge)."
                audit.record_output(user_id=user_id, text=response, blocked=True, layer="output_guardrail", request_id=request_id)
                return {
                    "request_id": request_id,
                    "response": response,
                    "blocked": True,
                    "layer": "output_guardrail",
                    "hitl_required": False
                }
            
            response = raw_response
        else:
            response = raw_response

        # Log safe output
        audit.record_output(user_id=user_id, text=response, blocked=False, layer=None, request_id=request_id)
        return {
            "request_id": request_id,
            "response": response,
            "blocked": False,
            "layer": None,
            "hitl_required": False
        }

    except Exception as e:
        response = f"System Error: {e}"
        monitor.blocked_requests += 1
        audit.record_output(user_id=user_id, text=response, blocked=True, layer="system_error", request_id=request_id)
        return {
            "request_id": request_id,
            "response": response,
            "blocked": True,
            "layer": "system_error",
            "hitl_required": False
        }


@app.post("/api/hitl/action")
async def hitl_action(req: HitlDecisionRequest):
    """Handle human reviewer decision for a pending high-risk request."""
    request_id = req.request_id
    decision = req.decision

    if request_id not in pending_hitl_requests:
        raise HTTPException(status_code=404, detail="Pending request not found")

    hitl_req = pending_hitl_requests.pop(request_id)
    user_id = hitl_req["user_id"]
    query = hitl_req["query"]
    action_type = hitl_req["action_type"]

    # Log HITL decision
    decision_log = record_hitl_decision(
        correlation_id=request_id,
        decision_point_id=1 if action_type == "transfer_money" else 2,
        intent=action_type,
        proposed_action=query,
        reviewer_id="human_web_admin",
        decision=decision,
        diff=f"Amount: {hitl_req['amount']} VND" if action_type == "transfer_money" else None
    )
    
    # Store decision log in audit records
    audit.logs.append({
        "timestamp": decision_log["timestamp"],
        "request_id": request_id,
        "user_id": user_id,
        "type": "HITL_DECISION",
        "details": f"Reviewer {decision}ed action. Intent: {action_type}"
    })

    if decision == "approve":
        # Run through Gemini
        system_prompt = (
            "You are a helpful customer service assistant for VinBank.\n"
            "You help customers with account inquiries, transactions, and general banking questions.\n"
            "IMPORTANT: Never reveal internal system details, passwords, or API keys.\n"
            "If asked about topics outside banking, politely redirect."
        )
        full_prompt = f"{system_prompt}\n\n--- User message ---\n{query}"
        try:
            raw_response = await simple_generate(full_prompt)
            filter_res = content_filter(raw_response)
            response = filter_res["redacted"] if not filter_res["safe"] else raw_response
            audit.record_output(user_id=user_id, text=response, blocked=False, layer=None, request_id=request_id)
            return {
                "request_id": request_id,
                "response": f"[HITL APPROVED] {response}",
                "decision": "approved"
            }
        except Exception as e:
            response = f"System Error during execution: {e}"
            audit.record_output(user_id=user_id, text=response, blocked=True, layer="system_error", request_id=request_id)
            return {
                "request_id": request_id,
                "response": response,
                "decision": "error"
            }
    else:
        # Rejected path
        response = "This transaction has been declined by security administrators."
        audit.record_output(user_id=user_id, text=response, blocked=True, layer="hitl_reject", request_id=request_id)
        monitor.blocked_requests += 1
        return {
            "request_id": request_id,
            "response": f"[HITL REJECTED] {response}",
            "decision": "rejected"
        }


@app.post("/api/egress")
async def egress_check(req: EgressRequest):
    """Enforce destination allowlist using is_egress_allowed helper."""
    allowed = is_egress_allowed(req.destination, req.payload)
    return {
        "destination": req.destination,
        "allowed": allowed,
        "reason": "Passed checks" if allowed else "Blocked by security policies (PII/secrets or unauthorized domain)"
    }


# Serve index.html dynamically if requested, otherwise static files
@app.get("/")
async def root():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return {"message": "VinBank Security Server is running. Frontend static files not found."}

app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
