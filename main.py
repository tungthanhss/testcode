"""
Tool luyện tập cá nhân: chụp màn hình -> hỏi DeepSeek Vision API -> lấy đáp án.

Chạy nền, lắng nghe global hotkey trên Windows bằng cách poll
GetAsyncKeyState (ổn định hơn hook của thư viện `keyboard` khi chạy
qua Remote Desktop / máy cloud, nơi hook tầng thấp thường không bắt
được phím do RDP bơm vào).
Mọi hành động đều im lặng (chỉ log ra console), không popup/toast.

    Ctrl + Click trái    Chụp màn hình, thêm vào hàng chờ ảnh
    Ctrl + Click phải    Gửi TẤT CẢ ảnh trong hàng chờ lên DeepSeek Vision
    Ctrl + Click giữa    Gõ giả lập đáp án mới nhất vào cửa sổ đang focus
    Ctrl + Shift         Xoá sạch ảnh và xoá rỗng log_file

Lưu ý thiết kế: nếu một hotkey là TẬP CON của hotkey khác (vd cấu hình
"ctrl" và "ctrl+mouseleft" cùng lúc), hotkey ngắn hơn sẽ tự trigger ngay
khi bạn giữ phần chung đó, trước khi kịp bấm nốt phần còn lại — gây kích
hoạt nhầm liên tục. Hotkey mặc định ở trên không dính lỗi này vì
"ctrl+shift" không phải tập con của 3 tổ hợp Ctrl+chuột kia (không chứa
Shift) và ngược lại.

Lưu ý khi dùng qua phần mềm remote/cloud gaming (DstationClient, VMware,
Citrix, Parsec...):
  - Tránh tổ hợp chứa Alt (Ctrl+Alt+...) — nhiều client chặn riêng để
    chuyển tiếp Ctrl+Alt+Del sang máy remote.
  - Tránh PHÍM SỐ hàng trên (1-9) — client cloud gaming thường chiếm độc
    quyền chúng ở tầng driver (game dùng để chọn vũ khí/item), nên
    GetAsyncKeyState không bao giờ đọc được.
  - Ưu tiên phím tiện ích đơn lẻ (ScrollLock/Pause/NumLock/Home/End/
    Insert/PageUp/PageDown) — game hầu như không dùng tới.
  - Dùng 1 phím đơn thay vì tổ hợp: tránh được lỗi các modifier bị client
    can thiệp làm chớp tắt, khiến 2-3 phím không bao giờ "cùng nhấn".
"""

import base64
import ctypes
import os
import sys
import threading
import time
from datetime import datetime

import keyboard  # chỉ dùng để gõ giả lập, không dùng để bắt hotkey
import mss
import mss.tools
from openai import OpenAI

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.txt")
ENTRY_SEPARATOR = "---"


# --------------------------------------------------------------------------- #
# Bắt hotkey bằng GetAsyncKeyState (poll) — ổn định qua RDP/cloud
# --------------------------------------------------------------------------- #

_VK_MAP = {}
for _i in range(1, 13):
    _VK_MAP[f"f{_i}"] = 0x70 + (_i - 1)          # F1-F12
for _i in range(13, 25):
    _VK_MAP[f"f{_i}"] = 0x7C + (_i - 13)         # F13-F24
for _c in "abcdefghijklmnopqrstuvwxyz":
    _VK_MAP[_c] = ord(_c.upper())
for _c in "0123456789":
    _VK_MAP[_c] = ord(_c)
_VK_MAP.update({
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B, "windows": 0x5B,
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "esc": 0x1B, "escape": 0x1B,
    "scrolllock": 0x91,
    "capslock": 0x14,
    "pause": 0x13,
    "printscreen": 0x2C,
    "numlock": 0x90,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    # Modifier trái/phải riêng biệt (dùng khi muốn phân biệt 2 bên)
    "lshift": 0xA0, "rshift": 0xA1,
    "lctrl": 0xA2, "rctrl": 0xA3,
    "lalt": 0xA4, "ralt": 0xA5,
    # Nút chuột — hữu ích khi phần mềm remote/cloud gaming chiếm hết bàn phím
    "mouseleft": 0x01,
    "mouseright": 0x02,
    "mousemiddle": 0x04,
    "mouse4": 0x05,   # nút phụ bên hông (back)
    "mouse5": 0x06,   # nút phụ bên hông (forward)
})

_GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState


def _is_key_down(vk_code):
    return bool(_GetAsyncKeyState(vk_code) & 0x8000)


def parse_hotkey(spec):
    """'ctrl+alt+1' -> [0x11, 0x12, 0x31]. Ném ValueError nếu tên phím lạ."""
    vk_codes = []
    for part in spec.split("+"):
        name = part.strip().lower()
        if name not in _VK_MAP:
            raise ValueError(f"Không nhận diện được phím '{name}' trong hotkey '{spec}'")
        vk_codes.append(_VK_MAP[name])
    return vk_codes


def poll_hotkeys(hotkeys, stop_event, poll_interval=0.03):
    """hotkeys: list[(vk_codes, callback)]. Edge-triggered, chạy callback ở thread riêng."""
    was_down = [False] * len(hotkeys)
    while not stop_event.is_set():
        for idx, (vk_codes, callback) in enumerate(hotkeys):
            down_now = all(_is_key_down(vk) for vk in vk_codes)
            if down_now and not was_down[idx]:
                threading.Thread(target=callback, daemon=True).start()
            was_down[idx] = down_now
        time.sleep(poll_interval)


def _vk_name(vk_code):
    for name, code in _VK_MAP.items():
        if code == vk_code and len(name) > 1:
            return name
    if 0x30 <= vk_code <= 0x39:
        return chr(vk_code)
    if 0x41 <= vk_code <= 0x5A:
        return chr(vk_code)
    return f"0x{vk_code:02X}"


def debug_key_scanner():
    """Chẩn đoán: in ra MỌI phím vật lý vừa được nhấn, theo thời gian thực.

    Dùng để xác định xem tiến trình có nhận được tín hiệu bàn phím nào từ
    máy cloud hay không (nếu không có gì hiện ra dù bấm bất kỳ phím nào,
    nghĩa là phần mềm remote/console đang chặn input trước khi tới Windows).
    """
    print("=== DEBUG KEY SCANNER ===")
    print("Hãy bấm thử các phím Ctrl, Alt, phím số 1, hoặc bất kỳ phím nào khác.")
    print("Nếu KHÔNG có dòng nào hiện ra dù bấm gì, phần mềm remote đang chặn")
    print("bàn phím trước khi tới được Windows (không phải lỗi của tool này).")
    print("Ctrl+C để thoát.\n")
    was_down = [False] * 256
    try:
        while True:
            for vk in range(1, 255):
                down = _is_key_down(vk)
                if down and not was_down[vk]:
                    print(f"  [NHẤN] vk=0x{vk:02X}  ({_vk_name(vk)})")
                was_down[vk] = down
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nDừng debug scanner.")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

DEFAULTS = {
    "hotkey_capture": "ctrl+mouseleft",
    "hotkey_send": "ctrl+mouseright",
    "hotkey_paste": "ctrl+mousemiddle",
    "hotkey_clear": "ctrl+shift",
    "model": "deepseek-v4-flash-vision-exp",
    "base_url": "https://api.deepseek.com",
    "api_key": "",
    "prompt": "Đây là ảnh chụp màn hình một bài toán/câu hỏi. Hãy trả lời CHỈ đáp án cuối cùng.",
    "log_file": "answers.log",
    "screenshot_folder": "screenshots/",
    "typing_delay": "0.03",
}


def load_config(path):
    """Đọc config dạng key=value. Chỉ tách ở dấu '=' đầu tiên."""
    cfg = dict(DEFAULTS)
    if not os.path.exists(path):
        print(f"[!] Không tìm thấy {path}, dùng giá trị mặc định.")
        return cfg

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip()
    return cfg


# --------------------------------------------------------------------------- #
# Trạng thái runtime
# --------------------------------------------------------------------------- #

config = {}
base_dir = os.path.dirname(os.path.abspath(__file__))
screenshot_dir = ""
log_path = ""
typing_delay = 0.01

pending_images = []          # hàng chờ: danh sách đường dẫn ảnh
queue_lock = threading.Lock()
api_lock = threading.Lock()  # đảm bảo chỉ 1 request API tại một thời điểm
client = None

typing_lock = threading.Lock()
typing_active = False            # đang trong tiến trình gõ giả lập
typing_cancel = threading.Event()  # bật lên để yêu cầu dừng gõ giữa chừng


def resolve(path_value):
    """Đường dẫn tương đối được tính theo thư mục chứa script."""
    if os.path.isabs(path_value):
        return path_value
    return os.path.normpath(os.path.join(base_dir, path_value))


# --------------------------------------------------------------------------- #
# Chụp màn hình
# --------------------------------------------------------------------------- #

def on_capture():
    try:
        os.makedirs(screenshot_dir, exist_ok=True)
        filename = datetime.now().strftime("shot_%Y%m%d_%H%M%S_%f") + ".png"
        filepath = os.path.join(screenshot_dir, filename)

        with mss.mss() as sct:
            # monitors[0] = toàn bộ các màn hình gộp lại
            shot = sct.grab(sct.monitors[0])
            mss.tools.to_png(shot.rgb, shot.size, output=filepath)

        with queue_lock:
            pending_images.append(filepath)
            count = len(pending_images)

        print(f"Đã chụp ảnh {count} -> {filename}")
    except Exception as exc:
        print(f"[!] Lỗi khi chụp màn hình: {exc}")


# --------------------------------------------------------------------------- #
# Gửi toàn bộ ảnh lên DeepSeek Vision API
# --------------------------------------------------------------------------- #

def image_data_url(path):
    """Đọc PNG và chuyển thành data URL để gửi trực tiếp tới vision model."""
    with open(path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")
    return "data:image/png;base64," + encoded


def append_answer(text):
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    existing = ""
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            existing = f.read()

    with open(log_path, "a", encoding="utf-8") as f:
        if existing.strip():
            if not existing.endswith("\n"):
                f.write("\n")
            f.write(ENTRY_SEPARATOR + "\n")
        f.write(text.rstrip() + "\n")


def do_send(images):
    if client is None:
        # Chưa có api_key -> chế độ test, không gọi API thật
        answer = (
            f"[MOCK - chưa có API key] Giả lập đáp án cho {len(images)} ảnh, "
            f"thời gian {datetime.now().strftime('%H:%M:%S')}"
        )
        append_answer(answer)
        print(f"[TEST MODE] Đã 'gửi' {len(images)} ảnh, ghi đáp án giả vào log")
        return

    user_content = [{"type": "text", "text": config["prompt"]}]
    for path in images:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": image_data_url(path)},
        })

    # API có thể trả 503 khi quá tải theo đợt -> thử lại vài lần
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=config["model"],
                messages=[{"role": "user", "content": user_content}],
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
            )
            answer = (response.choices[0].message.content or "").strip()

            if not answer:
                print("[!] API trả về rỗng, không ghi log.")
                return

            append_answer(answer)
            print(f"Đã gửi {len(images)} ảnh, nhận đáp án ({len(answer)} ký tự)")
            return
        except Exception as exc:
            if "503" in str(exc) and attempt < 2:
                print(f"[!] Model quá tải, thử lại lần {attempt + 2}/3...")
                time.sleep(2)
                continue
            print(f"[!] Lỗi khi gọi API: {exc}")
            return


def on_send():
    with queue_lock:
        if not pending_images:
            print("Hàng chờ rỗng, bỏ qua.")
            return
        images = list(pending_images)

    # Xử lý tuần tự: nếu đang có request chạy thì bỏ qua lần bấm này
    if not api_lock.acquire(blocking=False):
        print("Đang xử lý request trước, bỏ qua.")
        return

    try:
        # Clear hàng chờ trong bộ nhớ (không xoá file trên disk)
        with queue_lock:
            pending_images.clear()

        print(f"Đang gửi {len(images)} ảnh tới {config['model']}...")
        do_send(images)
    finally:
        api_lock.release()


# --------------------------------------------------------------------------- #
# Gõ giả lập đáp án mới nhất
# --------------------------------------------------------------------------- #

def read_last_entry():
    if not os.path.exists(log_path):
        return ""
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = [
        part.strip()
        for part in content.split("\n" + ENTRY_SEPARATOR + "\n")
        if part.strip()
    ]
    return entries[-1] if entries else ""


def on_paste():
    """Toggle: đang gõ -> dừng; không gõ -> gõ lại từ đầu."""
    global typing_active

    with typing_lock:
        if typing_active:
            typing_cancel.set()
            return

        text = read_last_entry()
        if not text:
            print("Log rỗng, không có gì để gõ.")
            return

        typing_active = True
        typing_cancel.clear()

    try:
        # Chờ người dùng nhả phím tắt trước khi gõ giả lập
        time.sleep(0.3)

        typed = 0
        for ch in text:
            if typing_cancel.is_set():
                print(f"Đã dừng ở ký tự {typed}/{len(text)} (bấm lại để gõ từ đầu)")
                return
            keyboard.write(ch)
            typed += 1
            time.sleep(typing_delay)

        print(f"Đã gõ {typed} ký tự")
    except Exception as exc:
        print(f"[!] Lỗi khi gõ: {exc}")
    finally:
        with typing_lock:
            typing_active = False


# --------------------------------------------------------------------------- #
# Xoá sạch
# --------------------------------------------------------------------------- #

def on_clear():
    try:
        removed = 0
        if os.path.isdir(screenshot_dir):
            for name in os.listdir(screenshot_dir):
                path = os.path.join(screenshot_dir, name)
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                        removed += 1
                    except OSError as exc:
                        print(f"[!] Không xoá được {name}: {exc}")

        with open(log_path, "w", encoding="utf-8"):
            pass

        with queue_lock:
            pending_images.clear()

        print(f"Đã xóa toàn bộ ({removed} ảnh + log)")
    except Exception as exc:
        print(f"[!] Lỗi khi xoá: {exc}")


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #

def main():
    global config, screenshot_dir, log_path, typing_delay, client

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if "--debug-keys" in sys.argv:
        debug_key_scanner()
        return 0

    config = load_config(CONFIG_PATH)
    screenshot_dir = resolve(config["screenshot_folder"])
    log_path = resolve(config["log_file"])

    try:
        typing_delay = float(config["typing_delay"])
    except ValueError:
        typing_delay = 0.01
        print("[!] typing_delay không hợp lệ, dùng 0.01")

    api_key = config["api_key"].strip()
    if api_key:
        client = OpenAI(
            api_key=api_key,
            base_url=config.get("base_url", "https://api.deepseek.com"),
        )
    else:
        client = None
        print("[!] Chưa điền api_key -> chạy ở TEST MODE (F7 sẽ ghi đáp án giả, không gọi API thật).")

    os.makedirs(screenshot_dir, exist_ok=True)

    try:
        hotkeys = [
            (parse_hotkey(config["hotkey_capture"]), on_capture),
            (parse_hotkey(config["hotkey_send"]), on_send),
            (parse_hotkey(config["hotkey_paste"]), on_paste),
            (parse_hotkey(config["hotkey_clear"]), on_clear),
        ]
    except ValueError as exc:
        print(f"[!] Lỗi cấu hình hotkey: {exc}")
        return 1

    stop_event = threading.Event()
    poller = threading.Thread(
        target=poll_hotkeys, args=(hotkeys, stop_event), daemon=True
    )
    poller.start()

    print("=" * 52)
    print(f"  Model     : {config['model']}")
    print(f"  Ảnh lưu ở : {screenshot_dir}")
    print(f"  Log       : {log_path}")
    print(f"  {config['hotkey_capture'].upper()} chụp | "
          f"{config['hotkey_send'].upper()} gửi | "
          f"{config['hotkey_paste'].upper()} gõ | "
          f"{config['hotkey_clear'].upper()} xoá")
    print("  Ctrl+C để thoát.")
    print("=" * 52)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        print("\nĐã thoát.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
