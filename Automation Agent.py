from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import getpass, time, sys, traceback

SHORT = 4
MED = 12
LONG = 30

def click_element_with_fallback(wait, locators):
    for loc in locators:
        try:
            elm = wait.until(EC.element_to_be_clickable(loc))
            elm.click()
            return True
        except Exception:
            continue
    return False

def find_password_element(driver, wait, timeout=25):
    """Try many ways to find the visible password input; return the WebElement or None."""
    end = time.time() + timeout
    while time.time() < end:
        candidates = []
        try:
            candidates.extend(driver.find_elements(By.NAME, "password"))
        except:
            pass
        try:
            candidates.extend(driver.find_elements(By.XPATH, "//input[@type='password']"))
        except:
            pass
        try:
            candidates.extend(driver.find_elements(By.XPATH, "//input[@aria-label='Enter your password']"))
        except:
            pass
        for c in candidates:
            try:
                if c.is_displayed() and c.is_enabled():
                    return c
            except:
                pass
        time.sleep(0.5)
    return None

def js_set_value_and_dispatch(driver, element, value):
    """Set element.value via JS and dispatch input & change events to mimic typing."""
    script = """
    const el = arguments[0];
    const val = arguments[1];
    el.focus();
    el.value = val;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    """
    driver.execute_script(script, element, value)

def wait_for_any(driver, wait, locators, timeout=10):
    """
    Wait for the first locator (By, selector) that becomes present and return that element.
    locators: list of (By, selector)
    """
    end = time.time() + timeout
    while time.time() < end:
        for loc in locators:
            try:
                elems = driver.find_elements(*loc)
                if elems:
                    for e in elems:
                        if e.is_displayed():
                            return e
            except Exception:
                continue
        time.sleep(0.3)
    return None

def try_force_inbox_and_wait(driver, wait, timeout=20):
    """Navigate to the inbox URL and wait for an inbox indicator (compose or main role)."""
    try:
        driver.get("https://mail.google.com/mail/u/0/#inbox")
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='main' or contains(@class,'aeF') or //div[text()='Compose']"))), timeout==timeout
        except:
            time.sleep(2)
        return True
    except Exception:
        return False

def main():
    email = input("Enter your Gmail ID: ").strip()
    pwd = getpass.getpass("Enter your Gmail Password: ")
    message_text = input("Message text to send: ").strip()

    fresh = input("Use fresh Chrome profile? (y/n) [y recommended]: ").strip().lower() or "y"

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    if fresh in ("y","yes"):
        options.add_argument("--user-data-dir=./tmp_chrome_profile")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, LONG)

    try:
        driver.get("https://accounts.google.com/ServiceLogin?service=mail&passive=true&continue=https://mail.google.com/")
        print("[INFO] Opened Google login for mail.")

        email_elem = wait.until(EC.element_to_be_clickable((By.ID, "identifierId")))
        email_elem.clear()
        email_elem.send_keys(email)
        if not click_element_with_fallback(wait, [(By.ID, "identifierNext"), (By.XPATH, "//button[@id='identifierNext']")]):
            email_elem.send_keys(Keys.ENTER)
        print("[INFO] Email submitted, waiting for password UI...")

        time.sleep(0.6)
        try:
            use_another = driver.find_elements(By.XPATH, "//*[contains(text(),'Use another account') or contains(text(),'Add account')]")
            if use_another:
                try:
                    use_another[0].click()
                    print("[INFO] Clicked 'Use another account' to proceed to password flow.")
                except:
                    pass
        except:
            pass

        pwd_elem = find_password_element(driver, wait, timeout=25)
        if not pwd_elem:
            print("[WARN] Password input not found quickly; waiting a few more seconds...")
            pwd_elem = find_password_element(driver, wait, timeout=15)

        if not pwd_elem:
            print("[ERROR] Password input not found. Possible causes: CAPTCHA, SSO redirect, or page changed.")
            print("Try: use fresh profile, check network, or open the login flow manually to inspect.")
            return

        try:
            pwd_elem.click()
            time.sleep(0.15)
            pwd_elem.clear()
            pwd_elem.send_keys(pwd)
            print("[INFO] Sent password via send_keys (attempt 1).")
        except Exception as e:
            print("[WARN] send_keys failed on password field; will try JS method. Error:", e)
            try:
                js_set_value_and_dispatch(driver, pwd_elem, pwd)
                print("[INFO] Password set via JS fallback.")
            except Exception as e2:
                print("[ERROR] JS fallback failed:", e2)
                return

        clicked = click_element_with_fallback(wait, [(By.ID, "passwordNext"), (By.XPATH, "//button[@id='passwordNext']"), (By.XPATH, "//div[@id='passwordNext']")])
        if not clicked:
            try:
                pwd_elem.send_keys(Keys.ENTER)
            except:
                pass
        print("[INFO] Submitted password; now forcing inbox URL and checking state...")

        try_force_inbox_and_wait(driver, wait, timeout=10)

        body_text = ""
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        except:
            pass

        if ("create an account" in body_text and "sign in" in body_text) or driver.find_elements(By.XPATH, "//a[contains(., 'Sign in') or contains(., 'Sign in')]") or driver.find_elements(By.XPATH, "//button[contains(., 'Sign in') or contains(., 'Sign in')]"):
            print("[INFO] Detected Gmail landing/marketing page with Sign in. Attempting a single retry of the login flow...")
            try:
                clicked_signin = False
                signin_candidates = driver.find_elements(By.XPATH, "//a[contains(., 'Sign in') or //button[contains(., 'Sign in')]]")
                for s in signin_candidates:
                    try:
                        if s.is_displayed():
                            s.click()
                            clicked_signin = True
                            break
                    except:
                        continue
                driver.get("https://accounts.google.com/ServiceLogin?service=mail&passive=true&continue=https://mail.google.com/")
                try:
                    email_elem = wait.until(EC.element_to_be_clickable((By.ID, "identifierId")))
                    email_elem.clear(); email_elem.send_keys(email)
                    if not click_element_with_fallback(wait, [(By.ID, "identifierNext"), (By.XPATH, "//button[@id='identifierNext']")]):
                        email_elem.send_keys(Keys.ENTER)
                    time.sleep(0.6)
                    pwd_elem = find_password_element(driver, wait, timeout=20)
                    if not pwd_elem:
                        print("[ERROR] Password field not found on retry. Aborting.")
                        return
                    pwd_elem.click(); time.sleep(0.15); pwd_elem.clear(); pwd_elem.send_keys(pwd)
                    if not click_element_with_fallback(wait, [(By.ID, "passwordNext"), (By.XPATH, "//button[@id='passwordNext']")]):
                        pwd_elem.send_keys(Keys.ENTER)
                    print("[INFO] Retry login submitted; forcing inbox again.")
                    try_force_inbox_and_wait(driver, wait, timeout=12)
                except Exception as e:
                    print("[ERROR] Retry login failed:", e)
            except Exception as e:
                print("[WARN] Failed to click Sign in; attempted direct login retry anyway. Error:", e)

        inbox_ok = False
        try:
            compose_present = len(driver.find_elements(By.XPATH, "//div[text()='Compose' or @aria-label='Compose']")) > 0
            main_present = len(driver.find_elements(By.XPATH, "//div[@role='main' or contains(@class,'aeF')]")) > 0
            if compose_present or main_present:
                inbox_ok = True
        except:
            inbox_ok = False

        if not inbox_ok:
            print("[ERROR] Inbox did not load after forcing the inbox URL / retry. This usually means Google requires additional verification (2FA, CAPTCHA) or blocked automation.")
            print("Try: use a fresh profile, ensure no 2FA on the test account, or consider using an SMTP fallback for sending emails.")
            return

        print("[INFO] Inbox detected — proceeding to compose.")

        try:
            print("[INFO] Opening stable composer URL...")
            driver.get("https://mail.google.com/mail/u/0/?view=cm&fs=1&to=scittest@auditram.com")
            time.sleep(2)
        except Exception as e:
            print("[ERROR] Could not open composer URL:", e)
            return

        try:
            subject_elem = None
            try:
                subject_elem = wait.until(EC.presence_of_element_located((By.NAME, "subject")),)
            except:
                subject_elem = wait_for_any(driver, wait, [
                    (By.NAME, "subjectbox"),
                    (By.XPATH, "//input[@name='subjectbox']"),
                    (By.XPATH, "//input[@aria-label='Subject']")
                ], timeout=10)

            if subject_elem:
                try:
                    subject_elem.click()
                    subject_elem.clear()
                    subject_elem.send_keys("Automated Test Email")
                    print("[INFO] Subject filled.")
                except Exception:
                    print("[WARN] Could not set subject via send_keys; continuing.")
            else:
                print("[WARN] Subject field not found; continuing without subject.")
        except Exception as e:
            print("[WARN] Subject handling error:", e)

        try:
            body_elem = wait_for_any(driver, wait, [
                (By.XPATH, "//div[@aria-label='Message Body']"),
                (By.XPATH, "//div[@role='textbox' and @aria-label]"),
                (By.XPATH, "//div[@role='textbox' and @contenteditable='true']"),
                (By.CSS_SELECTOR, "div.Am.Al.editable"),
            ], timeout=15)

            if not body_elem:
                print("[ERROR] Message body area not found. Composer may not have loaded. Exiting.")
                return

            try:
                body_elem.click()
                time.sleep(0.25)
                body_elem.send_keys(message_text)
                print("[INFO] Message body filled via send_keys.")
            except Exception:
                try:
                    driver.execute_script("""
                        const el = arguments[0];
                        const val = arguments[1];
                        if (el.isContentEditable) {
                            el.innerText = val;
                        } else {
                            el.value = val;
                        }
                        el.dispatchEvent(new Event('input', {bubbles:true}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                    """, body_elem, message_text)
                    print("[INFO] Message body set via JS fallback.")
                except Exception as e:
                    print("[ERROR] Failed to set message body:", e)
                    return
        except Exception as e:
            print("[ERROR] Composer/body wait error:", e)
            return

        try:
            send_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[text()='Send' or @aria-label='Send']")),)
            send_btn.click()
            print("[INFO] Send clicked.")
        except Exception:
            try:
                body_elem.click()
                body_elem.send_keys(Keys.CONTROL, Keys.ENTER)
                print("[INFO] Sent via Ctrl+Enter fallback.")
            except Exception as e:
                print("[ERROR] Could not send email:", e)
                return

        time.sleep(2)
        print("[SUCCESS] Send triggered. Please confirm in Sent folder if needed.")

    except Exception as ex:
        print("[EXCEPTION] Failed:", str(ex))
        traceback.print_exc()
    finally:
        print("Closing browser in 5 seconds...")
        time.sleep(5)
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    main()