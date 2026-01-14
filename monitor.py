import requests
import re
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION ---
# Alienware URLs
ALIENWARE_GIVEAWAY_URL = "https://eu.alienwarearena.com/ucf/Giveaway"
ALIENWARE_VAULT_URL = "https://eu.alienwarearena.com/marketplace/game-vault"

# Lenovo Configuration
LENOVO_URL = "https://gaming.lenovo.com/game-key-drops"
LENOVO_API_URL = "https://api.bettermode.com/"
LENOVO_SPACE_ID = "y4nnEocBKMA2"

# IDs που θεωρούμε "Active" ή "Coming Soon" στο Lenovo
LENOVO_VALID_STATUS_IDS = [
    "AmAI_EO502mWht5Fb6OE0", # Active (Standard)
    "d18QrMHpWMZMD1C4kJRZI", # Active (Alternative)
    "X7FhO8Z5w0QXFFnoFHVpZ"  # Coming Soon
]

STATE_FILE = "state.json"

# Διάβασε το Topic από το περιβάλλον (GitHub) ή βάλε το δικό σου εδώ (PC)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or "ΤΟ_ΔΙΚΟ_ΣΟΥ_TOPIC_ΕΔΩ" 

# Headers (Brave Style)
HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'en-US,en;q=0.6',
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Brave";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-gpc': '1'
}

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

def send_notification(message, title="Giveaway Alert", priority="default"):
    if not NTFY_TOPIC or NTFY_TOPIC == "ΤΟ_ΔΙΚΟ_ΣΟΥ_TOPIC_ΕΔΩ":
        print(f"⚠️ Skipping notification (no topic): {title}")
        return
    
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode('utf-8'),
            headers={
                "Title": title,
                "Priority": priority,
            }
        )
        resp.raise_for_status()
        print(f"✅ Notification sent: {title}")
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")

def parse_iso_date(date_str):
    """Βοηθητική για να διαβάζουμε ημερομηνίες ISO (ακόμα και με το Z στο τέλος)"""
    if not date_str: return None
    try:
        # Καθαρίζουμε εισαγωγικά αν υπάρχουν
        clean_str = date_str.replace('"', '').replace("'", "")
        # Αντικατάσταση Z με +00:00 για συμβατότητα με παλιότερες Python
        clean_str = clean_str.replace('Z', '+00:00')
        return datetime.fromisoformat(clean_str)
    except Exception as e:
        # print(f"Date parse error: {e}")
        return None

# --- ALIENWARE CHECKS ---
def check_alienware_giveaway(current_state):
    print("Checking Alienware Giveaway...")
    try:
        response = requests.get(ALIENWARE_GIVEAWAY_URL, headers=HEADERS)
        response.raise_for_status()
        content = response.text

        title_match = re.search(r'js-widget-title">([^<]+)<', content)
        current_title = title_match.group(1).strip() if title_match else None

        keys_match = re.search(r'var countryKeys\s*=\s*(\{.*?\});', content, re.DOTALL)
        current_keys = 0
        if keys_match:
            try:
                keys_data = json.loads(keys_match.group(1))
                max_keys = 0
                for country, data in keys_data.items():
                    if isinstance(data, dict):
                        for key_level, count in data.items():
                            if isinstance(count, int) and count > max_keys:
                                max_keys = count
                current_keys = max_keys
            except:
                pass

        print(f"   Found: {current_title} (Keys: {current_keys})")

        last_title = current_state.get("alienware_giveaway_title")
        
        if current_title and current_title != last_title:
            msg = f"New Alienware Giveaway!\nTitle: {current_title}\nKeys: {current_keys}"
            send_notification(msg, "Alienware Alert")
            current_state["alienware_giveaway_title"] = current_title

    except Exception as e:
        print(f"❌ Error checking Alienware giveaway: {e}")

def check_alienware_vault(current_state):
    print("Checking Alienware Vault...")
    try:
        response = requests.get(ALIENWARE_VAULT_URL, headers=HEADERS)
        response.raise_for_status()
        content = response.text

        disabled_match = re.search(r'data-product-disabled="(true|false)"', content)
        is_disabled_str = disabled_match.group(1) if disabled_match else "true"
        
        status_str = "Closed" if is_disabled_str == "true" else "Open"
        print(f"   Vault Status: {status_str}")

        last_status = current_state.get("alienware_vault_status")
        
        if last_status is not None and last_status != status_str:
            msg = f"Alienware Vault Status Changed!\nNew Status: {status_str}"
            send_notification(msg, "Alienware Vault")
        
        current_state["alienware_vault_status"] = status_str

    except Exception as e:
        print(f"❌ Error checking Alienware Vault: {e}")

# --- LENOVO CHECKS ---
def get_lenovo_token():
    try:
        r = requests.get(LENOVO_URL, headers=HEADERS)
        if r.status_code != 200: return None
        match = re.search(r'"accessToken":"([^"]+)"', r.text)
        return match.group(1) if match else None
    except Exception as e:
        print(f"❌ Lenovo Token Error: {e}")
        return None

def check_lenovo_giveaways(current_state):
    print("Checking Lenovo Gaming...")
    token = get_lenovo_token()
    if not token:
        print("⚠️ Skipping Lenovo check (No Token found)")
        return

    query = """
    query GetSpacePosts($spaceId: ID!, $limit: Int!) {
      posts(spaceIds: [$spaceId], limit: $limit, orderBy: publishedAt, reverse: true) {
        nodes {
          id
          title
          url
          fields {
            key
            value
          }
        }
      }
    }
    """

    api_headers = HEADERS.copy()
    api_headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Origin": "https://gaming.lenovo.com",
        "Referer": LENOVO_URL
    })

    try:
        response = requests.post(
            LENOVO_API_URL, 
            json={"query": query, "variables": {"spaceId": LENOVO_SPACE_ID, "limit": 50}}, 
            headers=api_headers
        )
        data = response.json()
        
        if 'errors' in data:
            print(f"❌ Lenovo API Error: {data['errors']}")
            return

        posts = data.get('data', {}).get('posts', {}).get('nodes', [])
        
        # Ανάκτηση των αποθηκευμένων giveaways (ή δημιουργία νέου λεξικού αν δεν υπάρχει)
        # Η δομή τώρα είναι: { "ID": { "title": "...", "start_date": "...", "reminded_24h": false, ... } }
        saved_giveaways = current_state.get("lenovo_giveaways", {})
        
        # Αν υπήρχε η παλιά λίστα (lenovo_known_ids), τη σβήνουμε ή την αγνοούμε
        # για να περάσουμε στο νέο σύστημα.

        current_active_ids = [] # Για να ξέρουμε ποια είναι ακόμα ζωντανά
        
        now_utc = datetime.now(timezone.utc)

        for post in posts:
            is_active = False
            status_val = "Unknown"
            start_date_str = None

            # Ανάλυση πεδίων (Status & Start Date)
            for field in post['fields']:
                if field['key'] == 'status':
                    status_val = field['value'].replace('"', '').replace('[', '').replace(']', '').replace('\\', '')
                    if status_val in LENOVO_VALID_STATUS_IDS:
                        is_active = True
                
                if field['key'] == 'start_date':
                    start_date_str = field['value']

            if is_active:
                post_id = post['id']
                post_title = post['title']
                current_active_ids.append(post_id)
                
                # Έλεγχος αν το έχουμε ξαναδεί
                if post_id not in saved_giveaways:
                    print(f"   Found NEW active drop: {post_title}")
                    send_notification(f"New Lenovo Drop Detected!\n{post_title}", "Lenovo Alert", "high")
                    
                    # Αποθήκευση στο state
                    saved_giveaways[post_id] = {
                        "title": post_title,
                        "start_date": start_date_str,
                        "status": status_val,
                        "reminded_24h": False,
                        "reminded_30m": False
                    }
                else:
                    # Το ξέρουμε ήδη, ας ελέγξουμε για reminders!
                    giveaway_data = saved_giveaways[post_id]
                    giveaway_data["status"] = status_val # Ενημέρωση status (π.χ. από Coming Soon σε Active)
                    
                    # Αν έχουμε ημερομηνία έναρξης
                    if start_date_str:
                        start_dt = parse_iso_date(start_date_str)
                        
                        if start_dt:
                            time_left = start_dt - now_utc
                            
                            # Reminder 24 ώρες πριν (μέσα στο παράθυρο 23h - 24h)
                            # Ή απλά αν είναι λιγότερο από 24h και δεν έχουμε ειδοποιήσει
                            if timedelta(hours=0) < time_left <= timedelta(hours=24):
                                if not giveaway_data.get("reminded_24h"):
                                    print(f"   ⏰ 24h Reminder for: {post_title}")
                                    send_notification(f"⏰ Reminder: Starts in < 24h!\n{post_title}", "Lenovo Reminder", "high")
                                    giveaway_data["reminded_24h"] = True
                            
                            # Reminder 30 λεπτά πριν (μέσα στο παράθυρο 0 - 30m)
                            if timedelta(minutes=0) < time_left <= timedelta(minutes=30):
                                if not giveaway_data.get("reminded_30m"):
                                    print(f"   🔥 30m Reminder for: {post_title}")
                                    send_notification(f"🔥 HURRY: Starts in < 30m!\n{post_title}", "Lenovo Urgent", "urgent")
                                    giveaway_data["reminded_30m"] = True
                            
                            # Αν ξεκίνησε ήδη (time_left < 0), θεωρητικά είναι Active τώρα.
        
        # Καθαρισμός (Garbage Collection)
        # Κρατάμε μόνο όσα υπάρχουν στο current_active_ids
        # Έτσι σβήνουμε αυτόματα τα expired/ended.
        clean_giveaways = {}
        for pid in current_active_ids:
            if pid in saved_giveaways:
                clean_giveaways[pid] = saved_giveaways[pid]
        
        # Ενημερώνουμε το state με τη καθαρή λίστα
        current_state["lenovo_giveaways"] = clean_giveaways
        
        # Σβήνουμε το παλιό κλειδί αν υπάρχει για να μην πιάνει χώρο
        if "lenovo_known_ids" in current_state:
            del current_state["lenovo_known_ids"]

        print(f"   Lenovo Check Done. Active items tracked: {len(clean_giveaways)}")

    except Exception as e:
        print(f"❌ Error checking Lenovo: {e}")

# --- MAIN EXECUTION ---
def main():
    state = load_state()
    
    check_alienware_giveaway(state)
    check_alienware_vault(state)
    check_lenovo_giveaways(state)
    
    save_state(state)

if __name__ == "__main__":
    main()
