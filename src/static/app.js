// Live web UI client logic for VinBank AI Agent Security Command Center

const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const chatMessages = document.getElementById("chat-messages");
const typingIndicator = document.getElementById("typing-indicator");

const statTotal = document.getElementById("stat-total");
const statBlocked = document.getElementById("stat-blocked");
const statRatelimit = document.getElementById("stat-ratelimit");
const statBlockrate = document.getElementById("stat-blockrate");

const hitlList = document.getElementById("hitl-list");
const auditList = document.getElementById("audit-list");

// User context
const userId = "web_playground_user_" + Math.random().toString(36).substring(2, 6);

// Event Listeners
sendBtn.addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Switch tabs for templates playground
function switchTab(tabName) {
    document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".template-grid").forEach(grid => grid.classList.remove("active"));
    
    // Find active tab btn and activate
    const activeBtn = Array.from(document.querySelectorAll(".tab-btn")).find(btn => btn.innerText.toLowerCase().includes(tabName));
    if (activeBtn) activeBtn.classList.add("active");
    
    document.getElementById(`${tabName}-templates`).classList.add("active");
}

// Click to fill template query and send immediately
function useTemplate(text) {
    chatInput.value = text;
    chatInput.focus();
    // Smooth scroll down input
    chatInput.scrollIntoView({ behavior: 'smooth' });
}

// Send Message Flow
async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = "";
    appendMessage("user", text);
    
    // Show typing loader
    typingIndicator.style.display = "flex";
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, user_id: userId })
        });
        
        const data = await res.json();
        typingIndicator.style.display = "none";

        if (data.hitl_required) {
            appendMessage("system", `🚨 Giao dịch cần được duyệt!
Hành động: ${data.hitl_details.action_type}
Độ tin cậy: ${data.hitl_details.confidence}
Lý do: ${data.hitl_details.reason}

Hệ thống đang tạm dừng và chờ duyệt của Reviewer. Bạn hãy bấm Approve hoặc Reject ở bảng điều khiển bên phải để tiếp tục.`, {
                hitl: true,
                reqId: data.request_id
            });
        } else {
            let meta = "";
            if (data.blocked) {
                meta = `❌ Bị chặn ở lớp: ${data.layer}`;
            } else {
                meta = `✅ Đã kiểm tra an toàn (output_guardrails)`;
            }
            appendMessage("system", data.response, { blocked: data.blocked, meta: meta });
        }
        
        // Refresh stats immediately
        updateMetrics();

    } catch (err) {
        typingIndicator.style.display = "none";
        appendMessage("system", `Error connecting to API server: ${err.message}`, { error: true });
    }
}

// Append message bubbles to chat pane
function appendMessage(role, text, options = {}) {
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("message", role);
    
    const avatar = document.createElement("div");
    avatar.classList.add("avatar");
    avatar.innerText = role === "user" ? "👤" : "🤖";
    
    const bubble = document.createElement("div");
    bubble.classList.add("bubble");
    
    const p = document.createElement("p");
    p.innerText = text;
    bubble.appendChild(p);

    if (options.meta) {
        const metaSpan = document.createElement("span");
        metaSpan.classList.add("meta-info");
        metaSpan.innerText = options.meta;
        bubble.appendChild(metaSpan);
    }
    
    if (options.hitl) {
        const actionDiv = document.createElement("div");
        actionDiv.style.marginTop = "10px";
        actionDiv.style.display = "flex";
        actionDiv.style.gap = "8px";
        
        const appBtn = document.createElement("button");
        appBtn.classList.add("btn-sm", "approve");
        appBtn.innerText = "Approve (Chấp nhận)";
        appBtn.onclick = () => submitHitl(options.reqId, "approve");
        
        const rejBtn = document.createElement("button");
        rejBtn.classList.add("btn-sm", "reject");
        rejBtn.innerText = "Reject (Từ chối)";
        rejBtn.onclick = () => submitHitl(options.reqId, "reject");
        
        actionDiv.appendChild(appBtn);
        actionDiv.appendChild(rejBtn);
        bubble.appendChild(actionDiv);
    }
    
    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    chatMessages.appendChild(msgDiv);
    
    // Auto-scroll chat down
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Poll & update live stats, logs, and HITL items
async function updateMetrics() {
    try {
        const res = await fetch("/api/metrics");
        const data = await res.json();
        
        // Update stats
        statTotal.innerText = data.total_requests;
        statBlocked.innerText = data.blocked_requests;
        statRatelimit.innerText = data.rate_limit_hits;
        statBlockrate.innerText = data.block_rate;

        // Update HITL List
        if (data.pending_hitl.length === 0) {
            hitlList.innerHTML = `<p class="empty-state">No pending actions requiring human authorization.</p>`;
        } else {
            hitlList.innerHTML = "";
            data.pending_hitl.forEach(item => {
                const div = document.createElement("div");
                div.classList.add("hitl-item");
                
                div.innerHTML = `
                    <div class="hitl-info">
                        <h4>⚠️ Giao dịch đang giữ: ${item.action_type.toUpperCase()}</h4>
                        <p><strong>Query:</strong> "${item.query}"</p>
                        <p><strong>Độ ưu tiên:</strong> ${item.priority} | <strong>Độ tin cậy:</strong> ${item.confidence}</p>
                        <p><strong>Lý do giữ:</strong> ${item.reason}</p>
                    </div>
                    <div class="hitl-actions">
                        <button class="btn-sm approve" onclick="submitHitl('${item.request_id}', 'approve')">Approve ✅</button>
                        <button class="btn-sm reject" onclick="submitHitl('${item.request_id}', 'reject')">Reject ❌</button>
                    </div>
                `;
                hitlList.appendChild(div);
            });
        }

        // Update Live Audit Logs
        if (data.audit_logs.length === 0) {
            auditList.innerHTML = `<p class="empty-state">No system events logged yet.</p>`;
        } else {
            auditList.innerHTML = "";
            data.audit_logs.forEach(log => {
                const div = document.createElement("div");
                div.classList.add("audit-item");
                
                let badgeClass = "allowed";
                let badgeText = "ALLOWED";
                
                if (log.blocked) {
                    badgeClass = "blocked";
                    badgeText = "BLOCKED";
                } else if (log.type === "HITL_DECISION") {
                    badgeClass = "hitl";
                    badgeText = "HITL DECISION";
                }

                div.innerHTML = `
                    <div class="audit-info">
                        <span class="audit-req-id">${log.request_id || "SYSTEM"} (${log.user_id})</span>
                        <span class="audit-text">${log.text || log.details}</span>
                    </div>
                    <span class="audit-badge ${badgeClass}">${badgeText}</span>
                `;
                auditList.appendChild(div);
            });
        }

    } catch (err) {
        console.error("Error fetching metrics:", err);
    }
}

// Approve / Reject a pending HITL request
async function submitHitl(requestId, decision) {
    try {
        const res = await fetch("/api/hitl/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ request_id: requestId, decision: decision })
        });
        const data = await res.json();
        
        // Append result of decision to chat
        appendMessage("system", data.response, { 
            meta: `🛡️ Giao dịch đã được ${decision === "approve" ? "Phê duyệt" : "Từ chối"} bởi Reviewer` 
        });
        
        // Refresh dashboards
        updateMetrics();
        
    } catch (err) {
        appendMessage("system", `Lỗi khi xử lý HITL: ${err.message}`, { error: true });
    }
}

// Simulate Egress allowlist checks
async function simulateEgress() {
    const dest = document.getElementById("egress-dest").value.trim();
    const payload = document.getElementById("egress-payload").value.trim();
    const resultBox = document.getElementById("egress-result");
    
    if (!dest) {
        alert("Please enter destination URL");
        return;
    }

    try {
        const res = await fetch("/api/egress", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ destination: dest, payload: payload })
        });
        const data = await res.json();
        
        resultBox.style.display = "block";
        if (data.allowed) {
            resultBox.className = "egress-result-box allowed";
            resultBox.innerText = `ALLOWED ✅ Egress connection allowed to: ${data.destination}`;
        } else {
            resultBox.className = "egress-result-box blocked";
            resultBox.innerText = `BLOCKED ❌ ${data.reason}`;
        }
        
    } catch (err) {
        resultBox.style.display = "block";
        resultBox.className = "egress-result-box blocked";
        resultBox.innerText = `Error checking egress: ${err.message}`;
    }
}

// Initial Loading
updateMetrics();
// Poll metrics every 2.5 seconds
setInterval(updateMetrics, 2500);
