import re
import ssl
import socket
import datetime
import requests
import numpy as np
import warnings
import whois
import tldextract
import dns.resolver
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml",
}

def normalize_url(url):
    url = str(url).strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url

def extract_hostname(url):
    parsed = urlparse(url)
    return parsed.netloc if parsed.netloc else parsed.path.split("/")[0]

def shannon_entropy(s):
    if not s:
        return 0
    probs = [s.count(c) / len(s) for c in set(s)]
    return -sum(p * np.log2(p) for p in probs)

def extract_url_features(url):
    url = normalize_url(url)
    parsed = urlparse(url)
    
    # Use tldextract for accurate separation
    ext = tldextract.extract(url)
    domain_part = ext.domain
    suffix = ext.suffix
    subdomain = ext.subdomain
    full_domain = f"{subdomain}.{domain_part}.{suffix}".strip(".")

    return [
        len(url),
        url.count("."),
        url.count("/"),
        full_domain.count("-"),
        1 if re.search(r"\d+\.\d+\.\d+\.\d+", full_domain) else 0,
        shannon_entropy(url),
        1 if "@" in url else 0,
        sum(c.isdigit() for c in url) / len(url),
        len(subdomain.split(".")) if subdomain else 0,
        len(suffix),             # TLD length
        1 if "https" in parsed.scheme else 0 # HTTPS check
    ]

def extract_domain_features(url):
    try:
        domain = extract_hostname(url)
        w = whois.whois(domain)
        
        # Helper to safely get first item if list
        def get_first(val):
            return val[0] if isinstance(val, list) else val

        # Creation Date (Age)
        creation_date = get_first(w.creation_date)
        
        age_days = 0
        creation_date_str = "Unknown"
        
        now = datetime.datetime.now(datetime.timezone.utc)

        if creation_date:
            # Ensure creation_date is timezone-aware or make it so
            if creation_date.tzinfo is None:
                creation_date = creation_date.replace(tzinfo=datetime.timezone.utc)
            else:
                creation_date = creation_date.astimezone(datetime.timezone.utc)
                
            age_days = (now - creation_date).days
            # Format: "Sep 15, 1997"
            creation_date_str = creation_date.strftime("%b %d, %Y")

        # Expiration Date
        expiration_date = get_first(w.expiration_date)
            
        expiry_days = 0
        if expiration_date:
            if expiration_date.tzinfo is None:
                expiration_date = expiration_date.replace(tzinfo=datetime.timezone.utc)
            else:
                 expiration_date = expiration_date.astimezone(datetime.timezone.utc)
            expiry_days = (expiration_date - now).days

        return {
            "domain_age_days": age_days,
            "domain_expiry_days": expiry_days,
            "creation_date": creation_date_str,
            "registrar": get_first(w.registrar) if w.registrar else "Unknown",
            "whois_server": get_first(w.whois_server) if w.whois_server else "Unknown"
        }
    except Exception:
        return {
            "domain_age_days": -1,  # -1 indicates unknown (WHOIS failed)
            "domain_expiry_days": -1,
            "creation_date": "Unknown",
            "registrar": "Unknown",
            "whois_server": "Unknown"
        }

def get_ssl_details(hostname):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=3) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        not_before = datetime.datetime.strptime(
            cert["notBefore"], "%b %d %H:%M:%S %Y %Z"
        )
        not_after = datetime.datetime.strptime(
            cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
        )
        
        # Ensure UTC comparison
        now = datetime.datetime.utcnow()
        age_days = (now - not_before).days
        validity_days = (not_after - not_before).days
        
        issuer_dict = dict(x[0] for x in cert['issuer'])
        issuer_common_name = issuer_dict.get('commonName', 'Unknown')
        organization = issuer_dict.get('organizationName', '')

        # Simple check for free DV certs often used by phishers (Let's Encrypt, cPanel, etc)
        # Note: Legitimate sites use these too, but it's a signal when combined with others.
        suspicious_issuers = ["R3", "cPanel", "Cloudflare"] 
        is_suspicious = any(s in issuer_common_name for s in suspicious_issuers)

        return {
            "valid": 1, 
            "age": age_days,
            "issuer": issuer_common_name,
            "organization": organization,
            "validity_days": validity_days,
            "is_suspicious": is_suspicious
        }
    except Exception:
        return {
            "valid": 0, 
            "age": 0,
            "issuer": "None",
            "organization": "",
            "validity_days": 0,
            "is_suspicious": False 
        }

def scan_html_content(url):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=6,
            allow_redirects=True
        )

        soup = BeautifulSoup(r.text, "html.parser")

        # Detect JS-rendered shells
        js_rendered = (
            'id="root"' in r.text or
            'id="app"' in r.text or
            "window." in r.text or
            len(r.text) < 2000
        )

        forms = soup.find_all("form")
        suspicious_form = 0

        for form in forms:
            action = form.get("action", "").strip()
            if not action:
                continue

            action_url = urljoin(url, action)

            if extract_hostname(action_url) != extract_hostname(url):
                suspicious_form = 1

        return {
            "has_forms": 1 if forms else 0,
            "suspicious_form": suspicious_form,
            "iframes": 1 if soup.find("iframe") else 0,
            "js_rendered": 1 if js_rendered else 0,
            "status": 1
        }

    except Exception:
        return {
            "has_forms": 0,
            "suspicious_form": 0,
            "iframes": 0,
            "js_rendered": 0,
            "status": 0
        }
