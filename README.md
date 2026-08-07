# Day 11 — Controlled Agent Security (2026)
**Họ và tên:** Nguyễn Trí Trung  
**MSSV:** 2A202601594  
**Môn học:** AICB-P1 — AI Agent Development  

Dự án này triển khai hệ thống **AI Agent Security Command Center** cho ngân hàng **VinBank** sử dụng cơ chế an ninh nhiều lớp (Defense-in-Depth) chống lại các cuộc tấn công tiêm độc chỉ thị (Prompt Injection), rate limit, rò rỉ dữ liệu nhạy cảm (PII/Secrets leak) và tích hợp phê duyệt con người (Human-in-the-Loop).

---

## 1. Cài đặt môi trường

```powershell
# 1) Tạo + kích hoạt virtualenv (khuyến nghị)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) API key
Copy-Item .env.example .env
# Mở .env, dán GOOGLE_API_KEY — lấy tại https://aistudio.google.com/apikey

# 3) Cài dependency trong venv
python -m pip install -U pip
pip install -r requirements.txt
```

---

## 2. Cách khởi chạy giao diện Web UI (Mới)

Chúng tôi đã xây dựng một **Web UI Command Center** hiện đại sử dụng Glassmorphism/Dark theme để bạn có thể tương tác trực tiếp với Agent và theo dõi các chỉ số bảo mật thời gian thực.

Để chạy ứng dụng Web UI:
```powershell
# 1) Đảm bảo virtualenv đã kích hoạt: .\.venv\Scripts\Activate.ps1
# 2) Khởi chạy app server từ thư mục gốc
python src/app.py
```
Sau đó truy cập trình duyệt tại địa chỉ: 👉 **[http://localhost:8000](http://localhost:8000)**

---

## 3. Cách chạy các phần kiểm tra tự động (CLI)

```powershell
cd src
# Chạy Part 1: Chạy 5 attacks nâng cao chống lại Unsafe Agent
python main.py --part 1

# Chạy Part 2: Kiểm thử tính năng chặn độc lập của các Guardrail (Input/Output)
python main.py --part 2

# Chạy Part 3: Chạy so sánh hiệu quả bảo mật (Before vs After) + Security Testing Pipeline
python main.py --part 3

# Chạy Part 4: Kiểm thử Confidence Router + cấu trúc duyệt HITL
python main.py --part 4

# Chạy Part 5: Chạy full test suite (Safe/Attack/Rate-limit/Edge) và xuất dữ liệu outputs/
python main.py --part 5
```

---

## 4. Tự kiểm thử chất lượng nộp bài (Pytest & Grade Check)

Đảm bảo tất cả các bài kiểm tra chất lượng của giáo viên đều vượt qua thành công:
```powershell
# Chạy smoke test
pytest tests/smoke -q

# Chạy public contract test
pytest tests/public -q
```
Các kết quả đầu ra sẽ được lưu tự động tại thư mục `outputs/` ở gốc repo bao gồm:
- `outputs/results.json`
- `outputs/audit_log.json`
- `outputs/metrics.json`
- `outputs/unsafe_attack_result.json`
- `outputs/guards_attack_result.json`
- `outputs/attack_results.json` (tổng hợp nộp bài)
