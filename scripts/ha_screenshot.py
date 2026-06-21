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

def take_screenshot(dashboard_path="/lovelace/0", output_file="/config/www/screenshots/screenshot.png", wait_time=10, zoom=100):
    username, password = get_credentials()

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1600')
    options.add_argument('--force-device-scale-factor=1')
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
            print("Logging in (shadow DOM)...")
            try:
                # HA:s login-fält ligger i shadow DOM - vanliga CSS-selektorer
                # når dem inte. Hitta, fyll och submitta via JavaScript istället.
                find_js = """
                function deepFind(root, pred){
                  for(const e of root.querySelectorAll('*')){
                    if(pred(e)) return e;
                    if(e.shadowRoot){const r=deepFind(e.shadowRoot, pred); if(r) return r;}
                  }
                  return null;
                }
                """
                wait = WebDriverWait(driver, 15)
                wait.until(lambda dr: dr.execute_script(find_js + """
                  return !!deepFind(document, e=>e.tagName==='INPUT'&&e.name==='username')
                      && !!deepFind(document, e=>e.tagName==='INPUT'&&e.name==='password');
                """))
                driver.execute_script(find_js + """
                  const U=arguments[0], P=arguments[1];
                  function setv(el,v){
                    el.value=v;
                    el.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
                    el.dispatchEvent(new Event('change',{bubbles:true,composed:true}));
                  }
                  setv(deepFind(document, e=>e.tagName==='INPUT'&&e.name==='username'), U);
                  setv(deepFind(document, e=>e.tagName==='INPUT'&&e.name==='password'), P);
                """, username, password)
                time.sleep(0.5)
                # Klicka login-knappen (mwc-button, ej ögat/checkboxen)
                clicked = driver.execute_script(find_js + """
                  const b=deepFind(document, e=>
                    (e.tagName==='HA-BUTTON'||e.tagName==='MWC-BUTTON'||e.tagName==='HA-PROGRESS-BUTTON')
                    && /log\\s*in|logga\\s*in/i.test(e.textContent||''));
                  if(b){b.click(); return b.tagName;}
                  return false;
                """)
                print(f"Login submitted (button clicked: {clicked})...")
                time.sleep(8)
            except Exception as e:
                print(f"Login error: {repr(e)}")
        
        # Extra wait for full rendering
        print(f"Waiting {wait_time}s for full render...")
        time.sleep(wait_time)

        # Apply zoom if not 100%
        if zoom != 100:
            driver.execute_script(f"document.body.style.zoom='{zoom}%'")
            time.sleep(1)

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
    output = sys.argv[2] if len(sys.argv) > 2 else "/config/www/screenshots/screenshot.png"
    wait = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    zoom = int(sys.argv[4]) if len(sys.argv) > 4 else 100
    take_screenshot(dashboard, output, wait, zoom)
