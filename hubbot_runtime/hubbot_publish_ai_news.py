import os, json, sys, urllib.request, urllib.parse

TOKEN = os.environ["COMMUNITY_ESTAGE_TOKEN"]
BASE = "https://community.hubactually.com"
PROJECT = "56382"
HEADERS = {
    "Estage-Authorization": TOKEN,
    "Authorization": TOKEN,
    "Accept": "application/json",
}

def upload_image(image_path):
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{os.path.basename(image_path)}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + image_data + f"\r\n--{boundary}--\r\n".encode()
    
    req = urllib.request.Request(
        f"{BASE}/api/{PROJECT}/upload",
        data=body,
        headers={
            "Estage-Authorization": TOKEN,
            "Authorization": TOKEN,
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
        print(f"Upload response: {json.dumps(data, indent=2)}", file=sys.stderr)
        return data

def create_post(title, body_html, image_data=None):
    CATEGORY = {
        "id": "4496ab4b-8529-4a7e-9a31-588fe414d9b0",
        "name": "General",
        "permissions": "anyone",
        "order": 0,
        "createdAt": "2026-03-10T15:22:56.403936+00:00",
    }
    
    # Use previewImages array format (proper image objects) instead of previewURL
    # to ensure the image renders as a full landscape cover, not a small square thumbnail.
    preview_images = []
    if image_data:
        image_url = image_data.get("path", "") or image_data.get("url", "")
        image_id = image_data.get("id", "")
        # Extract id from URL if not provided directly (e.g. /uploads/images/1784984794669.png)
        if not image_id and image_url:
            parts = image_url.rstrip('/').split('/')
            if parts:
                last = parts[-1]
                # Remove extension
                image_id = last.split('.')[0] if '.' in last else last
        if image_url:
            preview_images.append({
                "id": image_id,
                "url": image_url,
                "type": "image"
            })
    
    payload = {
        "title": title,
        "description": body_html,
        "pinned": False,
        "category": CATEGORY,
        "previewURL": "",  # Empty string — cover images use previewImages, not previewURL
        "previewImage": None,
        "previewImages": preview_images,
        "emailMembers": False,
        "scheduled": None,
        "mentions": [],
        "ruleKey": None,
        "channel": None,
        "origin": BASE,
        "groupName": "HubActually",
    }
    
    req_data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/api/{PROJECT}/threads/create",
        data=req_data,
        headers={
            "Estage-Authorization": TOKEN,
            "Authorization": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
        print(f"Create response: {json.dumps(data, indent=2)}", file=sys.stderr)
        return data

if __name__ == "__main__":
    image_path = sys.argv[1] if len(sys.argv) > 1 else "/agent/stored_files/cms0dtb040k3f07adstult3ce_5948115c-4353-4c07-9f63-04dcacf496ae.png"
    
    # Upload image
    upload_resp = upload_image(image_path)
    
    title = "Worknet Launches AI-Native Platform That Runs a Full Business in 48 Hours"
    body_html = (
        "<p>Worknet announced a new AI-native platform that deploys six AI agents—development, marketing, sales, support, operations, and analytics—to build, brand, and run a business in under 48 hours. Founders describe their idea in plain language and the platform handles the rest: product is built, marketing stack goes live, lead campaigns start, and real customer data flows in. The subscription replaces a traditional team that would cost an estimated $21K–$49K per month before revenue.</p>"
        "<p>For HubActually members, this is a practical signal: the barrier to validating an idea is no longer the cost of hiring a team. The real question is whether you can describe your idea clearly enough for an AI crew to execute it.</p>"
        "<p>If you could describe one business idea and have an AI team build and run it within 48 hours, what would you test first?</p>"
        '<p>Source: <a href="https://thenyledger.com/markets/worknet-launches-ai-native-platform-to-build-and-run-a-full-business-in-48-hours/" target="_blank">https://thenyledger.com/markets/worknet-launches-ai-native-platform-to-build-and-run-a-full-business-in-48-hours/</a> </p>'
    )
    
    create_resp = create_post(title, body_html, upload_resp)
    print(json.dumps(create_resp, indent=2))
