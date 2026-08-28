# Screenshot to GitHub Copilot

Ứng dụng Windows chụp màn hình bằng hotkey, gửi ảnh tới GitHub Copilot
Enterprise và gõ lại câu trả lời. Ứng dụng dùng đăng nhập OAuth/SSO đã lưu
trong Windows Credential Manager; không cần và không lưu API key của model.

## Cài đặt

Yêu cầu Python 3.11 trở lên và tài khoản được cấp GitHub Copilot Enterprise.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m copilot download-runtime
```

Sao chép `config.example.txt` thành `config.txt` nếu chưa có, rồi chỉnh model,
prompt và hotkey khi cần.

## Đăng nhập Enterprise SSO

Với tổ chức nằm trên `github.com` và dùng SAML SSO:

```powershell
.\venv\Scripts\python.exe main.py --login
```

Lệnh sẽ hiện mã dùng một lần. Nhập mã đó trong trình duyệt, đăng nhập tài khoản Enterprise, bấm
**Authorize** cho tổ chức SAML SSO, sau đó chấp thuận GitHub Copilot CLI.

Nếu tổ chức dùng GitHub Enterprise Cloud có data residency, điền hostname
`*.ghe.com` vào `github_host` trong `config.txt` rồi chạy lại lệnh trên.

## Chạy

Nhấp đúp `run.bat` để chạy nhanh. File này tự dùng môi trường `venv`; nếu
chưa có thì sẽ tạo môi trường và cài dependencies từ `vendor/wheels` có sẵn
trong repository, hoàn toàn không tải thư viện từ PyPI. Bộ wheel hỗ trợ Windows
x64 với Python 3.11 đến 3.14.

Mỗi lần khởi động, ứng dụng kiểm tra trạng thái GitHub Copilot. Nếu chưa xác
thực, ứng dụng mở OAuth device flow và yêu cầu hoàn tất đăng nhập. Token sau đó
được Copilot CLI lưu an toàn trong Windows Credential Manager nên các lần chạy
sau không cần đăng nhập lại. Kết nối Internet vẫn cần thiết để xác thực GitHub,
tải Copilot CLI runtime ở lần đầu và gửi câu hỏi tới Copilot.

Hoặc chạy trực tiếp bằng PowerShell:

```powershell
.\venv\Scripts\python.exe main.py
```

- `Ctrl + click trái`: chụp và thêm ảnh vào hàng chờ
- `Ctrl + click phải`: gửi toàn bộ ảnh tới Copilot
- `Ctrl + click giữa`: gõ câu trả lời mới nhất
- `Ctrl + Shift`: xóa ảnh và log
