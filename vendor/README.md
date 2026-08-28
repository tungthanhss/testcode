# Offline Python dependencies

Thư mục `wheels/` chứa toàn bộ dependency của `requirements.txt` để `run.bat`
có thể cài đặt mà không kết nối PyPI. Các wheel native hiện hỗ trợ CPython
3.11, 3.12, 3.13 và 3.14 trên Windows x64.

Không xóa các file `.whl` nếu muốn cài project trên máy không truy cập được
PyPI. Khi thay đổi `requirements.txt`, cần tải lại cả dependency bắc cầu và
wheel `pydantic_core` tương ứng cho tất cả phiên bản Python được hỗ trợ.
