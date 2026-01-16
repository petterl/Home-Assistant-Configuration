#!/usr/bin/env python3
"""Take screenshots of Home Assistant dashboards with automated login."""
import sys
import os
import time
import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_credentials():
    try:
        with open('/config/secrets.yaml') as f:
            secrets = yaml.safe_load(f)
            return secrets.get('ha_username'), secrets.get('ha_password')
    except:
        return None, None

def take_screenshot(dashboard_path="/lovelace/0", output_file="/config/www/screenshot.png", wait_time=10):
    username, password = get_credentials()
    
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.binary_location = '/usr/bin/chromium'
    
    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        ha_base = "http://homeassistant:8123"
        full_url = f"{ha_base}{dashboard_path}"
        
        print(f"Loading: {full_url}")
        driver.get(full_url)
        time.sleep(4)
        
        if "auth" in driver.current_url and username and password:
            print("Logging in...")
            try:
                wait = WebDriverWait(driver, 10)
                username_field = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[name='username'], input[type='text']")))
                username_field.clear()
                username_field.send_keys(username)
                time.sleep(0.5)
                
                password_field = driver.find_element(By.CSS_SELECTOR, "input[name='password'], input[type='password']")
                password_field.clear()
                password_field.send_keys(password)
                time.sleep(0.5)
                password_field.send_keys(Keys.RETURN)
                
                print("Login submitted...")
                time.sleep(8)
            except Exception as e:
                print(f"Login error: {e}")
        
        # Extra wait for full rendering
        print(f"Waiting {wait_time}s for full render...")
        time.sleep(wait_time)
        
        print(f"Title: {driver.title}")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        driver.save_screenshot(output_file)
        print(f"Screenshot: {output_file}")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        driver.quit()

if __name__ == "__main__":
    dashboard = sys.argv[1] if len(sys.argv) > 1 else "/lovelace-elektricitet/oversikt"
    output = sys.argv[2] if len(sys.argv) > 2 else "/config/www/screenshot.png"
    wait = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    take_screenshot(dashboard, output, wait)
