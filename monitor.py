import requests
import re
import json
import os
import sys

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
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

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

def send_notification(message, title="Giveaway Alert"):
    if not NTFY_TOPIC:
        print(f"⚠️ Skipping notification (no topic): {title}")
        return
    
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode('utf-8'),
            headers={
                "Title": title,
                "Priority": "default",
            }
        )
        resp.raise_for_status()
        print(f"✅ Notification sent: {title}")
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")

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
        
        # Ειδοποίηση ΜΟΝΟ αν άλλαξε ο τίτλος του Alienware
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
        
        # Ειδοποίηση ΜΟΝΟ αν άλλαξε το status του Alienware Vault
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

    # Ζητάμε τα 50 τελευταία posts
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
        
        current_active_ids = []    # Όλα τα active IDs που βρήκαμε τώρα
        new_active_titles = []     # Μόνο οι τίτλοι των ΝΕΩΝ active

        # Παίρνουμε τη λίστα με τα IDs που ξέραμε από την προηγούμενη φορά
        known_ids = current_state.get("lenovo_known_ids", [])

        for post in posts:
            is_active = False
            # Έλεγχος Status
            for field in post['fields']:
                if field['key'] == 'status':
                    # Καθαρισμός του value από σκουπίδια JSON
                    raw_val = field['value'].replace('"', '').replace('[', '').replace(']', '').replace('\\', '')
                    if raw_val in LENOVO_VALID_STATUS_IDS:
                        is_active = True
                        break
            
            if is_active:
                post_id = post['id']
                post_title = post['title']
                
                # Το προσθέτουμε στη λίστα των τωρινών Active
                current_active_ids.append(post_id)

                # Αν αυτό το ID δεν υπήρχε στα known_ids, είναι ΚΑΙΝΟΥΡΙΟ
                if post_id not in known_ids:
                    print(f"   Found NEW active drop: {post_title}")
                    new_active_titles.append(post_title)
                else:
                    # Απλά για debug, να ξέρουμε ότι το είδαμε
                    # print(f"   Found existing drop: {post_title}")
                    pass
        
        # Στέλνουμε ειδοποίηση ΜΟΝΟ αν βρέθηκαν ΝΕΑ giveaways
        if new_active_titles:
            msg = "New Lenovo Drop(s):\n" + "\n".join(new_active_titles)
            send_notification(msg, "Lenovo Alert")
            print(f"🔔 Notification sent for {len(new_active_titles)} new items.")
        else:
            print("   No new Lenovo drops found.")

        # Αποθηκεύουμε ΟΛΑ τα active IDs στο state για την επόμενη φορά
        current_state["lenovo_known_ids"] = current_active_ids
        print(f"   Lenovo Check Done. Total Active in memory: {len(current_active_ids)}")

    except Exception as e:
        print(f"❌ Error checking Lenovo: {e}")

# --- MAIN EXECUTION ---
def main():
    # Φόρτωση προηγούμενης κατάστασης
    state = load_state()
    
    # Έλεγχος Alienware (ανεξάρτητος)
    check_alienware_giveaway(state)
    check_alienware_vault(state)
    
    # Έλεγχος Lenovo (ανεξάρτητος)
    check_lenovo_giveaways(state)
    
    # Αποθήκευση νέας κατάστασης
    save_state(state)

if __name__ == "__main__":
    main()
