#!/usr/bin/env python3
"""Google Drive from the cloud, with a service account — no SDK, stock python3 + openssl.

    python3 scripts/drive.py --check                     # who am I, can I see EnglishPractice, what is in it
    python3 scripts/drive.py --ls EnglishPractice/koreader
    python3 scripts/drive.py --get EnglishPractice/koreader/statistics.sqlite3 <dest>
    python3 scripts/drive.py --put <file> EnglishPractice/library [--name X]   # create or update
    python3 scripts/drive.py --selftest

Credential: GDRIVE_SA_JSON_B64 (the service-account key file, base64 on one line) or GDRIVE_SA_JSON
(raw JSON) as an environment variable — never in git, the Hub store, or chat. The account has to be
shared on the folders it should see (EnglishPractice; com.nll.asr for the recorder's uploads).

Auth is the plain OAuth2 JWT flow: RS256-sign a claim with the key (openssl dgst), trade it for a
bearer token at oauth2.googleapis.com. Downloads stream to disk (alt=media): nothing large ever
passes through a chat context.
"""
import base64, datetime as dt, io, json, mimetypes, os, pathlib, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER = "application/vnd.google-apps.folder"
ROOT_NAME = "EnglishPractice"
UA = "english-runbook/1.0"

def b64url(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def load_key():
    raw = os.environ.get("GDRIVE_SA_JSON")
    if not raw and os.environ.get("GDRIVE_SA_JSON_B64"):
        raw = base64.b64decode(os.environ["GDRIVE_SA_JSON_B64"].strip()).decode("utf-8")
    if not raw: return None
    k = json.loads(raw)
    if k.get("type") != "service_account" or not k.get("private_key") or not k.get("client_email"):
        raise SystemExit("drive: the credential is not a service-account key file")
    return k

def sign_rs256(private_key_pem, data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(private_key_pem); path = f.name
    try:
        return subprocess.run(["openssl", "dgst", "-sha256", "-sign", path], input=data, capture_output=True, check=True).stdout
    finally:
        os.unlink(path)

def make_jwt(key, now=None, scope=SCOPE):
    now = int(now or time.time())
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claim = b64url(json.dumps({"iss": key["client_email"], "scope": scope, "aud": TOKEN_URL, "iat": now, "exp": now + 3600}).encode())
    signing_input = f"{header}.{claim}".encode()
    return signing_input.decode() + "." + b64url(sign_rs256(key["private_key"], signing_input))

_token = {"value": None, "exp": 0}
def token(key):
    if _token["value"] and time.time() < _token["exp"] - 60: return _token["value"]
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": make_jwt(key)}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = json.loads(r.read())
    _token.update(value=t["access_token"], exp=time.time() + int(t.get("expires_in", 3600)))
    return _token["value"]

def _req(key, url, data=None, headers=None, method=None, stream=False):
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + token(key), "User-Agent": UA, **(headers or {})})
    try:
        r = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"drive: HTTP {e.code} on {url.split('?')[0]}: {e.read().decode('utf-8', 'replace')[:300]}")
    return r if stream else json.loads(r.read() or b"{}")

def list_children(key, folder_id, fields="id,name,mimeType,size,modifiedTime,md5Checksum"):
    out, page = [], None
    while True:
        q = urllib.parse.urlencode({"q": f"'{folder_id}' in parents and trashed = false", "fields": f"nextPageToken,files({fields})", "pageSize": 200,
                                    "supportsAllDrives": "true", "includeItemsFromAllDrives": "true", **({"pageToken": page} if page else {})})
        r = _req(key, f"{API}/files?{q}")
        out += r.get("files", []); page = r.get("nextPageToken")
        if not page: return out

def find_roots(key, name):
    """Top-level folders shared with the account (a service account has no My Drive of its own)."""
    q = urllib.parse.urlencode({"q": f"name = '{name}' and mimeType = '{FOLDER}' and trashed = false", "fields": "files(id,name,owners(emailAddress))",
                                "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
    return _req(key, f"{API}/files?{q}").get("files", [])

def resolve(key, path):
    """'EnglishPractice/koreader/statistics.sqlite3' → file dict (or None). First segment = a shared root."""
    parts = [p for p in path.strip("/").split("/") if p]
    roots = find_roots(key, parts[0])
    if not roots: return None
    cur = roots[0]
    for name in parts[1:]:
        nxt = [f for f in list_children(key, cur["id"]) if f["name"] == name]
        if not nxt: return None
        cur = nxt[0]
    return cur

def walk(key, folder_id, prefix=""):
    """Every file below a folder, with its relative path (recordings live several levels down)."""
    for f in list_children(key, folder_id):
        rel = f"{prefix}{f['name']}"
        if f["mimeType"] == FOLDER: yield from walk(key, f["id"], rel + "/")
        else: yield rel, f

def download(key, file_id, dest):
    dest = pathlib.Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
    r = _req(key, f"{API}/files/{file_id}?alt=media&supportsAllDrives=true", stream=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk: break
            f.write(chunk)
    tmp.replace(dest); return dest

def upload(key, path, folder_id, name=None):
    """Create, or update in place when a file of that name already exists in the folder."""
    path = pathlib.Path(path); name = name or path.name
    existing = [f for f in list_children(key, folder_id) if f["name"] == name]
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    meta = {"name": name} if existing else {"name": name, "parents": [folder_id]}
    boundary = "english-runbook-" + str(int(time.time()))
    body = io.BytesIO()
    body.write(f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n".encode())
    body.write(f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode()); body.write(path.read_bytes()); body.write(f"\r\n--{boundary}--".encode())
    url = f"{UPLOAD}/files/{existing[0]['id']}?uploadType=multipart&supportsAllDrives=true" if existing else f"{UPLOAD}/files?uploadType=multipart&supportsAllDrives=true"
    return _req(key, url, data=body.getvalue(), method="PATCH" if existing else "POST", headers={"Content-Type": f"multipart/related; boundary={boundary}"})

def copy(key, file_id, folder_id, name=None):
    """Drive-side copy into a folder (no bytes through here) — how the shelf stocks the phone folder."""
    body = json.dumps({"parents": [folder_id], **({"name": name} if name else {})}).encode()
    return _req(key, f"{API}/files/{file_id}/copy?supportsAllDrives=true", data=body, method="POST", headers={"Content-Type": "application/json"})

def trash(key, file_id):
    return _req(key, f"{API}/files/{file_id}?supportsAllDrives=true", data=json.dumps({"trashed": True}).encode(), method="PATCH", headers={"Content-Type": "application/json"})

def selftest():
    # a throwaway RSA key: the JWT must verify with openssl against its public half
    with tempfile.TemporaryDirectory() as td:
        priv = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"], capture_output=True, check=True).stdout.decode()
        pub = subprocess.run(["openssl", "pkey", "-pubout"], input=priv.encode(), capture_output=True, check=True).stdout
        key = {"type": "service_account", "client_email": "x@y.iam.gserviceaccount.com", "private_key": priv}
        jwt = make_jwt(key, now=1789000000)
        h, c, s = jwt.split(".")
        claim = json.loads(base64.urlsafe_b64decode(c + "=="))
        assert claim["iss"] == key["client_email"] and claim["aud"] == TOKEN_URL and claim["exp"] - claim["iat"] == 3600 and claim["scope"] == SCOPE, claim
        sig = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        (pathlib.Path(td) / "pub.pem").write_bytes(pub); (pathlib.Path(td) / "sig").write_bytes(sig)
        v = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pathlib.Path(td) / "pub.pem"), "-signature", str(pathlib.Path(td) / "sig")],
                           input=f"{h}.{c}".encode(), capture_output=True)
        assert v.returncode == 0 and b"Verified OK" in v.stdout, v.stdout + v.stderr
        os.environ["GDRIVE_SA_JSON_B64"] = base64.b64encode(json.dumps(key).encode()).decode(); os.environ.pop("GDRIVE_SA_JSON", None)
        assert load_key()["client_email"] == key["client_email"]
    print("drive.py selftest: OK")

def main():
    a = sys.argv[1:]
    if "--selftest" in a: return selftest()
    key = load_key()
    if not key: print("drive: GDRIVE_SA_JSON_B64 / GDRIVE_SA_JSON not set"); return 3
    if "--check" in a:
        print(f"drive: service account {key['client_email']}")
        roots = find_roots(key, ROOT_NAME)
        print(f"drive: {ROOT_NAME!r} visible: {len(roots)}" + (f" (owner {roots[0].get('owners', [{}])[0].get('emailAddress')})" if roots else " — share the folder with the account"))
        if roots:
            for f in list_children(key, roots[0]["id"]): print(f"  {f['name']}{'/' if f['mimeType'] == FOLDER else ''}  {f.get('size', '')}")
        asr = find_roots(key, "com.nll.asr")
        print(f"drive: 'com.nll.asr' (the recorder's upload root) visible: {len(asr)}" + ("" if asr else " — share it too, or recordings stay invisible"))
        return 0 if roots else 1
    if "--ls" in a:
        f = resolve(key, a[a.index("--ls") + 1])
        if not f: print("not found"); return 1
        for c in list_children(key, f["id"]): print(f"{c['id']}\t{c['name']}{'/' if c['mimeType'] == FOLDER else ''}\t{c.get('size', '')}\t{c.get('modifiedTime', '')}")
        return 0
    if "--get" in a:
        i = a.index("--get"); f = resolve(key, a[i + 1])
        if not f: print("not found"); return 1
        print(download(key, f["id"], a[i + 2])); return 0
    if "--put" in a:
        i = a.index("--put"); folder = resolve(key, a[i + 2])
        if not folder: print("folder not found"); return 1
        name = a[a.index("--name") + 1] if "--name" in a else None
        r = upload(key, a[i + 1], folder["id"], name); print(f"uploaded {r.get('name')} ({r.get('id')})"); return 0
    print(__doc__); return 2

if __name__ == "__main__":
    sys.exit(main())
