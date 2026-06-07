import os
import json
import glob
from google_auth_oauthlib.flow import InstalledAppFlow

def main():
    print("=================================================================")
    print("          YOUTUBE OAUTH CREDENTIALS GENERATOR FOR BOT            ")
    print("=================================================================")
    print("\n Hướng dẫn:")
    print(" 1. Tải file client_secret_xxxx.json từ Google Cloud Console về.")
    print(" 2. Đổi tên file đó thành 'client_secret.json' và đặt cùng thư mục với script này.")
    print(" 3. Đảm bảo máy tính của bạn đã cài đặt các thư viện cần thiết:")
    print("    pip install google-auth-oauthlib google-api-python-client")
    print("\n=================================================================\n")

    client_secrets_file = "client_secret.json"

    if not os.path.exists(client_secrets_file):
        # Search for any file matching client_secret*.json in current dir
        matching = glob.glob("client_secret*.json")
        if matching:
            client_secrets_file = matching[0]
            print(f"[*] Tìm thấy file cấu hình: {client_secrets_file}")
        else:
            print("[-] LỖI: Không tìm thấy file 'client_secret.json'!")
            print("    Vui lòng copy file client_secret tải từ Google Cloud vào thư mục này.")
            input("\nNhấn Enter để thoát...")
            return

    # Scopes needed for YouTube uploads
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly"
    ]

    try:
        print("[*] Đang khởi tạo luồng xác thực Google OAuth...")
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, scopes=scopes)
        
        print("[*] Trình duyệt web sẽ tự động mở ra sau vài giây.")
        print("[*] Hãy đăng nhập và cấp quyền cho tài khoản YouTube của bạn.")
        
        # Run local server to complete the authorization code exchange
        creds = flow.run_local_server(host='localhost', port=0, success_message="Xác thực thành công! Bạn có thể đóng tab này.")
        
        # Build the JSON object
        creds_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "token_uri": creds.token_uri
        }
        
        output_file = "youtube_credentials.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(creds_data, f, indent=2)
            
        print("\n=================================================================")
        print("🎉 XÁC THỰC THÀNH CÔNG!")
        print("=================================================================")
        print(f"\n Tệp cấu hình chứa refresh_token đã được lưu tại:")
        print(f" -> {os.path.abspath(output_file)}")
        print("\n Việc tiếp theo:")
        print(" 1. Mở Bot Telegram, vào mục '🔑 Cài Đặt API/TOKEN'.")
        print(" 2. Chọn nền tảng '▶️ YouTube' và nhấn '➕ Thêm API/TOKEN' (hoặc '🔄 Cập Nhật').")
        print(" 3. Gửi tệp 'youtube_credentials.json' vừa tạo lên Bot.")
        print("\n=================================================================")
        
    except Exception as e:
        print(f"\n[-] Xảy ra lỗi trong quá trình xác thực: {e}")
        print("    Vui lòng kiểm tra lại cấu hình Redirect URIs của OAuth client ID trong")
        print("    Google Cloud (phải bao gồm http://localhost).")
        
    input("\nNhấn Enter để kết thúc...")

if __name__ == "__main__":
    main()
