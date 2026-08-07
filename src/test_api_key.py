"""
Test nhanh Gemini API key, KHÔNG qua ADK / agent framework.
Nếu vẫn 429 ở đây -> chắc chắn là vấn đề của API key/quota,
không phải do code pipeline/testing của bạn.

Cách chạy:
    pip install google-genai
    python test_api_key.py YOUR_API_KEY [model_name]

Ví dụ:
    python test_api_key.py AIzaSy... gemini-2.0-flash
"""
import sys
import json

def main():
    if len(sys.argv) < 2:
        print("Cách dùng: python test_api_key.py YOUR_API_KEY [model_name]")
        print("Model mặc định: gemini-2.0-flash")
        sys.exit(1)

    api_key = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "gemini-2.0-flash"

    try:
        from google import genai
    except ImportError:
        print("Chưa cài package. Chạy: pip install google-genai")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print(f"Đang test model: {model} ...")
    try:
        response = client.models.generate_content(
            model=model,
            contents="Xin chao, ban co hoat dong khong?",
        )
        print("\n✅ THÀNH CÔNG! Key hoạt động bình thường.")
        print("Phản hồi:", response.text)
    except Exception as e:
        print("\n❌ LỖI khi gọi API:")
        print(f"Loại lỗi: {type(e).__name__}")
        print(f"Chi tiết đầy đủ (repr):\n{repr(e)}")

        # Cố gắng in chi tiết quotaId / quotaMetric nếu có, để biết
        # là quota theo PHÚT hay theo NGÀY đang bị chặn.
        err_str = str(e)
        if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
            print("\n--- Đây là lỗi 429 (quota) ---")
            print("Tìm chữ 'quotaId' trong log ở trên:")
            print("  - Nếu thấy '...PerMinute...' -> đang vượt giới hạn request/phút, chỉ cần chờ.")
            print("  - Nếu thấy '...PerDay...'    -> quota NGÀY đã cạn, chờ không có tác dụng,")
            print("    phải đợi reset theo ngày (theo giờ Thái Bình Dương - Mỹ) hoặc bật billing.")
            print("  - Nếu KHÔNG thấy quotaId nào cả (giống log bạn đang gặp) -> nhiều khả năng")
            print("    là lỗi backend/đồng bộ hoá phía Google, không phải do bạn.")


if __name__ == "__main__":
    main()