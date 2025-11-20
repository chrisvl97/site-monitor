import requests
import re
import json
import os
import sys

# Configuration
GIVEAWAY_URL = "https://eu.alienwarearena.com/ucf/Giveaway"
VAULT_URL = "https://eu.alienwarearena.com/marketplace/game-vault"
STATE_FILE = "state.json"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def send_notification(message):
    if not NTFY_TOPIC:
        print(f"Skipping notification (no topic): {message}")
        return
    
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode('utf-8'),
            headers={
                "Title": "Alienware Arena Update",
                "Priority": "default",
            }
        )
        resp.raise_for_status()
        print(f"Notification sent: {message}")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def check_giveaway(current_state):
    print("Checking Giveaway...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(GIVEAWAY_URL, headers=headers)
        response.raise_for_status()
        content = response.text

        # Parse Title
        # Pattern: js-widget-title">(X)<
        title_match = re.search(r'js-widget-title">([^<]+)<', content)
        current_title = title_match.group(1).strip() if title_match else None

        # Parse Keys
        # Pattern: var countryKeys = { ... };
        # We need to extract the JSON object from the variable assignment.
        keys_match = re.search(r'var countryKeys\s*=\s*(\{.*?\});', content, re.DOTALL)
        current_keys = 0
        if keys_match:
            try:
                keys_json_str = keys_match.group(1)
                # The JSON might contain trailing commas or other JS-specific syntax that json.loads might dislike if not strict JSON.
                # However, the user snippet looks like valid JSON (keys quoted).
                # Let's try to load it.
                keys_data = json.loads(keys_json_str)
                
                # Calculate total keys. 
                # Structure: "CountryCode": {"1": count} or []
                # It seems "1" is the key for the count? Or maybe the level?
                # User example: "AC": {"1": 1353}
                # Let's sum up all values found in the dictionaries.
                # Note: It seems the count 1353 is repeated for many countries. 
                # It might be the *same* pool of keys available to all those countries.
                # If we sum them, we might get a huge number (1353 * 100 countries).
                # If it's a global pool, we should just take the max value found?
                # User said "check countryKeys generally and try to pull keys correctly".
                # If I see 1353 everywhere, it's likely the total available.
                # I will take the maximum value found across all countries to be safe, 
                # assuming it's a shared pool. If it were separate pools, the user would probably care about their specific country.
                # But since I don't know the user's country, reporting the max available keys seems like a good proxy for "are there keys?".
                
                max_keys = 0
                for country, data in keys_data.items():
                    if isinstance(data, dict):
                        for key_level, count in data.items():
                            if isinstance(count, int) and count > max_keys:
                                max_keys = count
                current_keys = max_keys
                
            except json.JSONDecodeError as e:
                print(f"Failed to parse countryKeys JSON: {e}")
        else:
            print("Could not find countryKeys variable.")

        print(f"Found Giveaway: {current_title} (Keys: {current_keys})")

        last_title = current_state.get("giveaway_title")
        
        # Logic: Notify if title changed
        if current_title and current_title != last_title:
            msg = f"New Giveaway Detected!\nTitle: {current_title}\nKeys Available: {current_keys}"
            send_notification(msg)
            current_state["giveaway_title"] = current_title
        
        # Update keys in state regardless, or maybe we only care about title change?
        # User said: "αν έχει αλλάξει ο τίτλος... τότε θα με ενημερώνει"
        # So we only notify on title change.
        
    except Exception as e:
        print(f"Error checking giveaway: {e}")

def check_vault(current_state):
    print("Checking Game Vault...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(VAULT_URL, headers=headers)
        response.raise_for_status()
        content = response.text

        # Parse Vault Status
        # Pattern: data-product-disabled="(X)"
        # If true -> Closed, else Open (if false or not present? User said "An einai true tote simainei vault kleisto allios anoixto")
        
        # We need to find the specific element. There might be multiple products? 
        # The user said "H pliroforia vrisketai sto data-product-disabled".
        # Assuming there's a main vault status or we just check the first one?
        # Usually Game Vault has one main status or multiple items.
        # Let's look for the first occurrence as a simple check, or maybe we should check if *any* is open?
        # User instructions were specific about the attribute. I will search for it.
        
        disabled_match = re.search(r'data-product-disabled="(true|false)"', content)
        is_disabled_str = disabled_match.group(1) if disabled_match else "true" # Default to closed if not found?
        
        is_closed = is_disabled_str == "true"
        status_str = "Closed" if is_closed else "Open"
        
        print(f"Vault Status: {status_str}")

        last_status = current_state.get("vault_status")
        
        # Notify on change
        if last_status is not None and last_status != status_str:
            msg = f"Game Vault Status Changed!\nNew Status: {status_str}"
            send_notification(msg)
        
        current_state["vault_status"] = status_str

    except Exception as e:
        print(f"Error checking vault: {e}")

def main():
    state = load_state()
    
    check_giveaway(state)
    check_vault(state)
    
    save_state(state)

if __name__ == "__main__":
    main()
