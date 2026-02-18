import cv2
import numpy as np
import pyautogui
import time
import os
import sys
import json
import logging
import ctypes
from PIL import Image

# 平台特定的导入
if sys.platform == 'win32':
    import win32gui
    import win32ui
    import win32con
    import win32api
    # 启用 Windows 高 DPI 感知，防止坐标偏移
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()
        
elif sys.platform == 'darwin':
    import subprocess
    import Quartz
    import AppKit
elif sys.platform == 'linux':
    import subprocess
    import Xlib
    import Xlib.display

def find_qq_video_window():
    """查找QQ视频通话窗口，返回窗口句柄或标识符"""
    try:
        if sys.platform == 'win32':
            windows = []
            def callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    window_title = win32gui.GetWindowText(hwnd)
                    # 匹配常见的QQ视频关键词
                    if any(keyword in window_title for keyword in ['视频通话', 'QQ视频', '视频', '通话']):
                        windows.append((hwnd, window_title))
                return True
            win32gui.EnumWindows(callback, windows)
            if windows:
                print(f"找到QQ视频通话窗口: {windows[0][1]}")
                return windows[0][0]
            return None
            
        elif sys.platform == 'darwin':
            script = '''
            tell application "System Events"
                tell process "QQ"
                    set windowList to every window whose name contains "视频通话" or name contains "QQ视频"
                    if (count of windowList) > 0 then
                        set {x, y} to position of first item of windowList
                        set {w, h} to size of first item of windowList
                        return (name of first item of windowList) & "|" & x & "," & y & "," & w & "," & h
                    else
                        return ""
                    end if
                end tell
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
            output = result.stdout.strip()
            if output:
                name, coords = output.split("|", 1)
                return {"name": name, "coords": coords}
            return None
                
        elif sys.platform == 'linux':
            for keyword in ['视频通话', 'QQ视频', '视频']:
                result = subprocess.run(['xdotool', 'search', '--name', keyword], capture_output=True, text=True)
                if result.stdout.strip():
                    return result.stdout.strip().split('\n')[0]
            return None
    except Exception as e:
        print(f"查找窗口出错: {e}")
        return None

def capture_window_screenshot(window_info=None):
    """截取指定窗口截图，修复Windows黑屏和偏移问题"""
    try:
        # --- Windows 修复逻辑 ---
        if sys.platform == 'win32' and window_info:
            hwnd = window_info
            # 获取窗口真实物理坐标
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width, height = right - left, bottom - top

            if width <= 0 or height <= 0:
                return capture_window_screenshot(None)

            # 准备设备上下文
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # 使用 PrintWindow 抓取内容 (参数3代表抓取内容，即使有硬件加速)
            # 如果 PrintWindow 失败，回退到 BitBlt
            result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)
            if result != 1:
                saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)

            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            im = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), 
                                 bmpstr, 'raw', 'BGRX', 0, 1)

            # 必须清理资源，防止GDI句柄泄漏
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            
            return im, (left, top, width, height)

        # --- macOS 逻辑 ---
        elif sys.platform == 'darwin' and window_info:
            if isinstance(window_info, dict) and "coords" in window_info:
                x, y, w, h = map(int, window_info["coords"].split(','))
                temp_file = f"temp_mac_cap.png"
                subprocess.run(['screencapture', '-R', f'{x},{y},{w},{h}', temp_file])
                if os.path.exists(temp_file):
                    im = Image.open(temp_file).convert('RGB')
                    os.remove(temp_file)
                    return im, (x, y, w, h)
            return capture_window_screenshot(None)

        # --- Linux 逻辑 ---
        elif sys.platform == 'linux' and window_info:
            temp_file = "temp_linux_cap.png"
            subprocess.run(['import', '-window', window_info, temp_file])
            if os.path.exists(temp_file):
                im = Image.open(temp_file).convert('RGB')
                os.remove(temp_file)
                return im, (0, 0, im.width, im.height)
            return capture_window_screenshot(None)

        # --- 全局回退方案 ---
        screenshot = pyautogui.screenshot()
        return screenshot, (0, 0, screenshot.width, screenshot.height)

    except Exception as e:
        print(f"截图出错: {e}")
        screenshot = pyautogui.screenshot()
        return screenshot, (0, 0, screenshot.width, screenshot.height)

def crop_image(image):
    """裁切图像，添加安全保护"""
    if image is None:
        return None
    
    width, height = image.size
    # 您要求的裁切参数
    left = 50
    top = 100
    right = width - 50
    bottom = height - 500 # 注意：如果窗口高度小于600，这里会报错
    
    # 安全检查：如果高度不足以这样裁切，自动调整
    if bottom <= top:
        bottom = height - 50 if height > 150 else height
    if right <= left:
        right = width - 10 if width > 20 else width
        
    return image.crop((left, top, right, bottom))

def upload_to_cos(local_file_path):
    """上传文件到腾讯云COS"""
    try:
        if not os.path.exists("config.json"):
            return False, None
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        
        tencent_config = config.get("TENCENT", {})
        cos_config = config.get("TENCENT_COS", {})
        
        if not cos_config.get("upload_enabled", False):
            return False, None
        
        from qcloud_cos import CosConfig, CosS3Client
        
        cos_cfg = CosConfig(
            Region=cos_config.get("region", "ap-beijing"),
            SecretId=tencent_config.get("secret_id"),
            SecretKey=tencent_config.get("secret_key"),
            Scheme='https'
        )
        client = CosS3Client(cos_cfg)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        remote_path = f"{cos_config.get('upload_path', 'screenshots/').strip('/')}/{timestamp}_shot.png"
        
        with open(local_file_path, 'rb') as fp:
            client.put_object(Bucket=cos_config.get("bucket"), Body=fp, Key=remote_path)
        
        url = client.get_presigned_download_url(
            Bucket=cos_config.get("bucket"), Key=remote_path, Expired=120
        )
        return True, url
    except Exception as e:
        print(f"COS上传失败: {e}")
        return False, None

def get_image(use_base64=False):
    """主函数：截图 -> 裁切 -> 保存/上传"""
    output_path = "images/image.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 1. 查找窗口
    qq_window = find_qq_video_window()
    
    # 2. 截图
    screenshot, _ = capture_window_screenshot(qq_window)
    if screenshot is None: return None
    
    # 3. 裁切
    cropped_image = crop_image(screenshot)
    
    # 4. 保存
    cropped_image.save(output_path)
    
    if use_base64:
        import base64
        with open(output_path, "rb") as f:
            return f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    else:
        success, url = upload_to_cos(output_path)
        return url if success else None

if __name__ == "__main__":
    # 测试运行
    result = get_image(use_base64=True)
    if result:
        print("截图并处理成功！")
        # print(result) # 如果是base64会非常长