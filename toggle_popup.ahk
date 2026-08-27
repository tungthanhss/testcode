#Requires AutoHotkey v2.0
#SingleInstance Force

; ====== CẤU HÌNH ======
; Đường dẫn tới file txt cần hiển thị (sửa lại theo ý bạn)
filePath := "D:\Test PCCP\Test PCCP\answers.log"
; =======================

popupGui := ""

TogglePopup(*) {
    global popupGui, filePath

    ; Nếu popup đang mở -> đóng lại
    if (popupGui != "" && IsObject(popupGui)) {
        try {
            popupGui.Destroy()
        }
        popupGui := ""
        return
    }

    ; Nếu chưa mở -> đọc file và hiện popup
    if !FileExist(filePath)
        return

    content := ""
    try {
        content := FileRead(filePath, "UTF-8")
    } catch {
        return
    }

    popupW := 600
    popupH := 600

    popupGui := Gui("+AlwaysOnTop +ToolWindow -Caption -Border", "Popup")
    popupGui.BackColor := "263747"          ; nền tối, sẽ làm trong suốt bên dưới
    popupGui.SetFont("s10 cB2C0CC", "Consolas")
    popupGui.Add("Edit", "ReadOnly Multi VScroll -E0x200 x0 y0 w" (popupW + 17) " h" popupH " Background263747 cB2C0CC vTextBox", content)

    ; Đóng popup khi mất focus (click ra ngoài)
    popupGui.OnEvent("Escape", (*) => ClosePopup())
    popupGui.OnEvent("Close", (*) => ClosePopup())

    ; Vị trí: sát cạnh trái màn hình, giữa theo chiều dọc
    posX := 10
    posY := (A_ScreenHeight - popupH) / 2

    popupGui.Show(Format("x{} y{} w{} h{}", posX, posY, popupW, popupH))

    ; Làm cả cửa sổ trong suốt (0 = trong suốt hoàn toàn, 255 = đục hoàn toàn)
    WinSetTransparent(210, popupGui.Hwnd)
}

ClosePopup() {
    global popupGui
    if (popupGui != "" && IsObject(popupGui)) {
        try {
            popupGui.Destroy()
        }
        popupGui := ""
    }
}

; ====== HOTKEYS ======
; Ctrl + nút Back (XButton1)
^XButton1::TogglePopup()
; Ctrl + nút Forward (XButton2)
^XButton2::TogglePopup()

; Nhấn Esc để đóng popup nhanh (chỉ khi popup đang mở và có focus)
#HotIf popupGui != "" && WinActive("ahk_id " (IsObject(popupGui) ? popupGui.Hwnd : 0))
Escape::ClosePopup()
#HotIf
