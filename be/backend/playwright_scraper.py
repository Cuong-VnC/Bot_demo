import logging
import asyncio
from playwright.async_api import async_playwright
import re
import urllib.parse

logger = logging.getLogger(__name__)

try:
    from playwright_stealth.stealth import Stealth
    stealth_available = True
except ImportError:
    stealth_available = False

def get_tiktok_fallback(url):
    match = re.search(r'@([a-zA-Z0-9_\.]+)', url)
    if match:
        return f"TikTok @{match.group(1)}"
    parts = url.rstrip('/').split('/')
    if parts:
        last = parts[-1].split('?')[0]
        if last.startswith('@'):
            return f"TikTok {last}"
    return "TikTok Channel"

def get_facebook_fallback(url):
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)
    
    if 'id' in query:
        return f"Facebook Profile {query['id'][0]}"
        
    people_match = re.search(r'/people/([^/]+)/', path)
    if people_match:
        name = urllib.parse.unquote(people_match.group(1))
        name = name.replace('-', ' ').replace('_', ' ').strip()
        return name
        
    parts = [p for p in path.split('/') if p]
    if parts:
        last = parts[-1]
        if last not in ('posts', 'videos', 'reels', 'photos', 'about', 'reviews'):
            name = urllib.parse.unquote(last)
            return name.replace('-', ' ').replace('_', ' ').strip()
        elif len(parts) > 1:
            name = urllib.parse.unquote(parts[-2])
            return name.replace('-', ' ').replace('_', ' ').strip()
            
    return "Facebook Page"

def normalize_facebook_url(url: str) -> list[str]:
    url = url.strip()
    if 'facebook.com' not in url and 'fb.watch' not in url:
        return [url]
        
    # If it is already video-specific, don't auto-expand
    if any(x in url for x in ('/videos', '/reels', '/watch', 'sk=videos', 'sk=reels_tab', '/posts')):
        return [url]
        
    # Profile pages e.g. profile.php?id=1000123456789
    if 'profile.php' in url and 'id=' in url:
        sep = '&' if '?' in url else '?'
        return [
            f"{url}{sep}sk=videos",
            f"{url}{sep}sk=reels_tab",
            url
        ]
        
    # General pages / profiles: e.g. https://www.facebook.com/username
    url_clean = url.rstrip('/')
    parsed = urllib.parse.urlparse(url_clean)
    path_parts = [p for p in parsed.path.split('/') if p]
    if not path_parts:
        return [url]
        
    return [
        f"{url_clean}/videos/",
        f"{url_clean}/reels/",
        url_clean
    ]

def parse_tiktok_cookies(cookie_input) -> list[dict]:
    if not cookie_input:
        return []
        
    cookies = []
    
    # If cookie_input is already parsed as a list of dicts from get_api_token
    if isinstance(cookie_input, list):
        if not cookie_input:
            return []
        first_item = cookie_input[0]
        if isinstance(first_item, dict) and 'name' in first_item and 'value' in first_item:
            for item in cookie_input:
                if isinstance(item, dict) and 'name' in item and 'value' in item:
                    domain = item.get('domain', '.tiktok.com')
                    if not domain.startswith('.'):
                        domain = '.' + domain
                    cookies.append({
                        'name': item['name'],
                        'value': str(item['value']),
                        'domain': domain,
                        'path': item.get('path', '/'),
                        'httpOnly': item.get('httpOnly', item['name'].lower() in ('sessionid', 'sessionid_ss')),
                        'secure': item.get('secure', True)
                    })
            return cookies
        else:
            # It's a list of multiple credentials or sessionids. Use the first one.
            return parse_tiktok_cookies(first_item)
        
    # If cookie_input is already parsed as a dictionary
    if isinstance(cookie_input, dict):
        for name, value in cookie_input.items():
            cookies.append({
                'name': name,
                'value': str(value),
                'domain': '.tiktok.com',
                'path': '/',
                'httpOnly': name.lower() in ('sessionid', 'sessionid_ss'),
                'secure': True
            })
        return cookies

    # Convert to string and strip
    cookie_str = str(cookie_input).strip()
    
    # 1. Check if it's a JSON array or object
    if (cookie_str.startswith('[') and cookie_str.endswith(']')) or cookie_str.startswith('{'):
        try:
            import json
            data = json.loads(cookie_str)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'name' in item and 'value' in item:
                        domain = item.get('domain', '.tiktok.com')
                        if not domain.startswith('.'):
                            domain = '.' + domain
                        cookies.append({
                            'name': item['name'],
                            'value': str(item['value']),
                            'domain': domain,
                            'path': item.get('path', '/'),
                            'httpOnly': item.get('httpOnly', item['name'].lower() in ('sessionid', 'sessionid_ss')),
                            'secure': item.get('secure', True)
                        })
            elif isinstance(data, dict):
                for name, value in data.items():
                    cookies.append({
                        'name': name,
                        'value': str(value),
                        'domain': '.tiktok.com',
                        'path': '/',
                        'httpOnly': name.lower() in ('sessionid', 'sessionid_ss'),
                        'secure': True
                    })
            if cookies:
                return cookies
        except Exception as e:
            logger.warning(f"Failed to parse TikTok cookie JSON: {e}")

    # 2. Check if it's key-value pair string (e.g. sessionid=xxx; ttwid=yyy)
    if '=' in cookie_str:
        parts = cookie_str.split(';')
        for part in parts:
            part = part.strip()
            if not part or '=' not in part:
                continue
            name, val = part.split('=', 1)
            name = name.strip()
            val = val.strip()
            cookies.append({
                'name': name,
                'value': val,
                'domain': '.tiktok.com',
                'path': '/',
                'httpOnly': name.lower() in ('sessionid', 'sessionid_ss'),
                'secure': True
            })
        if cookies:
            return cookies

    # 3. Plain sessionid value
    if cookie_str:
        cookies.append({
            'name': 'sessionid',
            'value': cookie_str,
            'domain': '.tiktok.com',
            'path': '/',
            'httpOnly': True,
            'secure': True
        })
        
    return cookies

def parse_facebook_cookies(cookie_input) -> list[dict]:
    if not cookie_input:
        return []
        
    cookies = []
    
    if isinstance(cookie_input, list):
        if not cookie_input:
            return []
        first_item = cookie_input[0]
        if isinstance(first_item, dict) and 'name' in first_item and 'value' in first_item:
            for item in cookie_input:
                if isinstance(item, dict) and 'name' in item and 'value' in item:
                    domain = item.get('domain', '.facebook.com')
                    if not domain.startswith('.'):
                        domain = '.' + domain
                    cookies.append({
                        'name': item['name'],
                        'value': str(item['value']),
                        'domain': domain,
                        'path': item.get('path', '/'),
                        'httpOnly': item.get('httpOnly', False),
                        'secure': item.get('secure', True)
                    })
            return cookies
        else:
            return parse_facebook_cookies(first_item)
        
    if isinstance(cookie_input, dict):
        for name, value in cookie_input.items():
            cookies.append({
                'name': name,
                'value': str(value),
                'domain': '.facebook.com',
                'path': '/',
                'httpOnly': False,
                'secure': True
            })
        return cookies

    cookie_str = str(cookie_input).strip()
    
    if (cookie_str.startswith('[') and cookie_str.endswith(']')) or cookie_str.startswith('{'):
        try:
            import json
            data = json.loads(cookie_str)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'name' in item and 'value' in item:
                        domain = item.get('domain', '.facebook.com')
                        if not domain.startswith('.'):
                            domain = '.' + domain
                        cookies.append({
                            'name': item['name'],
                            'value': str(item['value']),
                            'domain': domain,
                            'path': item.get('path', '/'),
                            'httpOnly': item.get('httpOnly', False),
                            'secure': item.get('secure', True)
                        })
            elif isinstance(data, dict):
                for name, value in data.items():
                    cookies.append({
                        'name': name,
                        'value': str(value),
                        'domain': '.facebook.com',
                        'path': '/',
                        'httpOnly': False,
                        'secure': True
                      })
            if cookies:
                return cookies
        except Exception as e:
            logger.warning(f"Failed to parse Facebook cookie JSON: {e}")

    if '=' in cookie_str:
        parts = cookie_str.split(';')
        for part in parts:
            part = part.strip()
            if not part or '=' not in part:
                continue
            name, val = part.split('=', 1)
            cookies.append({
                'name': name.strip(),
                'value': val.strip(),
                'domain': '.facebook.com',
                'path': '/',
                'httpOnly': False,
                'secure': True
            })
        if cookies:
            return cookies
            
    return cookies

async def _launch_stealth_browser(p, headless=True, platform=None):
    browser = await p.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"
        ]
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    
    # Try to load and inject cookies if database has session data for this platform
    if platform:
        try:
            import database
            token_platform = 'facebook_cookies' if platform == 'facebook' else platform
            token_data = database.get_api_token(token_platform)
            if token_data:
                if platform == 'tiktok':
                    cookies = parse_tiktok_cookies(token_data)
                    if cookies:
                        logger.info(f"Injecting {len(cookies)} TikTok cookies to Playwright context.")
                        await context.add_cookies(cookies)
                    else:
                        logger.warning("No valid TikTok cookies parsed from token data.")
                elif platform == 'facebook':
                    cookies = parse_facebook_cookies(token_data)
                    if cookies:
                        logger.info(f"Injecting {len(cookies)} Facebook cookies to Playwright context.")
                        await context.add_cookies(cookies)
                    else:
                        logger.warning("No valid Facebook cookies parsed from token data.")
        except Exception as cookie_err:
            logger.warning(f"Could not inject cookies for {platform}: {cookie_err}")
            
    page = await context.new_page()
    
    # Override navigator.webdriver to false/undefined
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # Apply playwright-stealth if available
    if stealth_available:
        try:
            await Stealth().apply_stealth_async(page)
        except Exception as stealth_err:
            logger.warning(f"Could not apply Playwright stealth: {stealth_err}")
            
    return browser, page


async def scrape_tiktok_videos(url: str, limit: int = 5) -> list[dict]:
    """
    Scrapes TikTok profile page for video URLs, IDs, and titles using Playwright.
    """
    videos = []
    logger.info(f"Playwright: Scraping TikTok videos from {url}")
    browser = None
    try:
        async with async_playwright() as p:
            browser, page = await _launch_stealth_browser(p, platform='tiktok')
            
            # Navigate with generous timeout
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for content to render (TikTok can be slow)
            await page.wait_for_timeout(6000)
            
            # Check for CAPTCHA or Login state to aid in diagnostics
            captcha_el = await page.query_selector('#captcha-verify-container, .captcha-verify-container, div[class*="captcha"]')
            if captcha_el:
                logger.warning("TikTok CAPTCHA detected! Scraping is blocked by a puzzle/slider CAPTCHA. Please ensure a valid session cookie is configured.")
            else:
                login_el = await page.query_selector('[data-e2e="nav-login-button"]')
                if login_el:
                    logger.info("TikTok Nav Login Button detected. Scraper is running in logged-out state (higher risk of CAPTCHA/blocking).")
                else:
                    logger.info("TikTok Scraper: Navigated successfully. No CAPTCHA or Login Button detected (logged-in state or clean session).")
            
            # Scroll to load more items
            num_scrolls = 25 if limit is None else 2
            last_height = await page.evaluate("document.body.scrollHeight")
            for scroll_i in range(num_scrolls):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 500)")
                    await page.wait_for_timeout(500)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        break
                last_height = new_height
            
            # Find links containing "/video/"
            links = await page.query_selector_all('a[href*="/video/"]')
            
            seen_ids = set()
            valid_idx = 1
            
            for link in links:
                if limit is not None and len(videos) >= limit:
                    break
                    
                href = await link.get_attribute("href")
                if not href:
                    continue
                
                # Check video ID pattern
                match = re.search(r'/video/(\d+)', href)
                if not match:
                    continue
                video_id = match.group(1)
                
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)
                
                # Standardize URL
                video_url = href
                if href.startswith('/'):
                    video_url = f"https://www.tiktok.com{href}"
                elif not href.startswith('http'):
                    # Relative link or something else
                    video_url = f"https://www.tiktok.com/{href.lstrip('/')}"
                
                # Extract title from alt attribute of image card or text
                title = ""
                img = await link.query_selector('img')
                if img:
                    title = await img.get_attribute("alt") or ""
                
                if not title:
                    # Get text content inside link
                    text = await page.evaluate('(el) => el.innerText', link)
                    if text:
                        title = text.split('\n')[0].strip()
                        
                if not title:
                    # Fallback: climb up to 4 parent levels and search for description class
                    try:
                        title = await page.evaluate('''
                            (linkEl) => {
                                let parent = linkEl;
                                for (let i = 0; i < 4; i++) {
                                    if (!parent || parent.tagName === "BODY") break;
                                    let descEl = parent.querySelector('[class*="DivDes"], [class*="desc"], [class*="caption"]');
                                    if (descEl) {
                                        return descEl.innerText || "";
                                    }
                                    parent = parent.parentElement;
                                }
                                return "";
                            }
                        ''', link)
                    except Exception:
                        pass
                        
                if not title:
                    title = f"TikTok Video {video_id}"
                
                title = title.strip()[:100]
                
                videos.append({
                    'index': valid_idx,
                    'title': title,
                    'url': video_url,
                    'id': video_id
                })
                valid_idx += 1
                
            logger.info(f"Playwright: Found {len(videos)} TikTok videos.")
    except Exception as e:
        logger.error(f"Playwright TikTok scraping failed: {e}")
    finally:
        if browser:
            try:
                await browser.close()
            except Exception as close_err:
                logger.error(f"Error closing TikTok scraper browser: {close_err}")
                
    return videos

async def scrape_facebook_videos(url: str, limit: int = 5) -> list[dict]:
    """
    Scrapes Facebook Page/Profile reels or videos using Playwright.
    """
    videos = []
    logger.info(f"Playwright: Scraping Facebook videos from {url}")
    target_urls = normalize_facebook_url(url)
    logger.info(f"Normalized Facebook targets: {target_urls}")
    
    browser = None
    try:
        async with async_playwright() as p:
            browser, page = await _launch_stealth_browser(p, platform='facebook')
            
            seen_ids = set()
            valid_idx = 1
            
            for target_url in target_urls:
                if limit is not None and len(videos) >= limit:
                    break
                    
                logger.info(f"Playwright Facebook: Navigating to sub-target {target_url}")
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(4000)
                except Exception as nav_err:
                    logger.warning(f"Failed to navigate to {target_url}: {nav_err}")
                    continue
                    
                # Dismiss popup if we can
                try:
                    close_btn = await page.query_selector('div[role="dialog"] div[aria-label="Đóng"], div[role="dialog"] div[aria-label="Close"]')
                    if close_btn:
                        await close_btn.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass
                
                # Scroll down to fetch lazy loaded items
                num_scrolls = 25 if limit is None else 2
                last_height = await page.evaluate("document.body.scrollHeight")
                for scroll_i in range(num_scrolls):
                    if limit is not None and len(videos) >= limit:
                        break
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 500)")
                        await page.wait_for_timeout(500)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(1000)
                        new_height = await page.evaluate("document.body.scrollHeight")
                        if new_height == last_height:
                            break
                    last_height = new_height
                    
                # Gather all links on the current page
                links = await page.query_selector_all('a')
                for link in links:
                    if limit is not None and len(videos) >= limit:
                        break
                        
                    href = await link.get_attribute("href")
                    if not href:
                        continue
                    
                    video_id = None
                    video_url = None
                    
                    # Check different Facebook video link types
                    if "/watch" in href and "v=" in href:
                        match = re.search(r'v=(\d+)', href)
                        if match:
                            video_id = match.group(1)
                            video_url = f"https://www.facebook.com/watch/?v={video_id}"
                    elif "/reel/" in href:
                        match = re.search(r'/reel/(\d+)', href)
                        if match:
                            video_id = match.group(1)
                            video_url = f"https://www.facebook.com/reel/{video_id}"
                    elif "/videos/" in href:
                        match = re.search(r'/videos/(\d+)', href)
                        if match:
                            video_id = match.group(1)
                            video_url = href if href.startswith('http') else f"https://www.facebook.com{href}"
                    
                    if not video_id:
                        continue
                        
                    if video_id in seen_ids:
                        continue
                    seen_ids.add(video_id)
                    
                    # Try getting description from surrounding post container
                    title = ""
                    try:
                        title = await page.evaluate('''
                            (linkEl) => {
                                let parent = linkEl;
                                // Climb up to 12 levels to find post container
                                for (let i = 0; i < 12; i++) {
                                    if (!parent || parent.tagName === "BODY") break;
                                    let msgEl = parent.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
                                    if (msgEl) {
                                        return msgEl.innerText || "";
                                    }
                                    parent = parent.parentElement;
                                }
                                
                                // Fallback to dir="auto"
                                parent = linkEl;
                                for (let i = 0; i < 12; i++) {
                                    if (!parent || parent.tagName === "BODY") break;
                                    let dirs = parent.querySelectorAll('div[dir="auto"], span[dir="auto"]');
                                    for (let dir of dirs) {
                                        let text = dir.innerText || "";
                                        if (text && text !== "Thích" && text !== "Bình luận" && text !== "Chia sẻ" && !text.includes("giờ")) {
                                            return text;
                                        }
                                    }
                                    parent = parent.parentElement;
                                }
                                return "";
                            }
                        ''', link)
                    except Exception:
                        pass
                        
                    if not title:
                        title = await link.get_attribute("aria-label") or ""
                    if not title:
                        text = await page.evaluate('(el) => el.innerText', link)
                        if text:
                            title = text.split('\n')[0].strip()
                            
                    if not title:
                        title = f"Facebook Video {video_id}"
                        
                    title = title.strip()[:100]
                    
                    videos.append({
                        'index': valid_idx,
                        'title': title,
                        'url': video_url,
                        'id': video_id
                    })
                    valid_idx += 1
                    
            logger.info(f"Playwright: Found {len(videos)} Facebook videos in total.")
    except Exception as e:
        logger.error(f"Playwright Facebook scraping failed: {e}")
    finally:
        if browser:
            try:
                await browser.close()
            except Exception as close_err:
                logger.error(f"Error closing Facebook scraper browser: {close_err}")
                
    return videos

async def scrape_tiktok_channel_info(url: str) -> tuple[str, str]:
    """
    Extracts TikTok user profile name and username using Playwright.
    """
    logger.info(f"Playwright: Extracting TikTok channel info for {url}")
    channel_name = "TikTok Channel"
    channel_id = url.rstrip('/').split('/')[-1].replace('@', '').split('?')[0]
    browser = None
    try:
        async with async_playwright() as p:
            browser, page = await _launch_stealth_browser(p, platform='tiktok')
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            
            final_url = page.url
            match = re.search(r'@([a-zA-Z0-9_\.]+)', final_url)
            if match:
                channel_id = match.group(1)
                
            # Select nickname or subtitles
            name_el = await page.query_selector('h1[data-e2e="user-title"], h2[data-e2e="user-subtitle"]')
            if name_el:
                channel_name = await name_el.inner_text()
            else:
                page_title = await page.title()
                if page_title and page_title.strip() not in ("TikTok", "Log In", "Đăng nhập"):
                    channel_name = page_title.split('|')[0].strip()
                    
            if not channel_name or channel_name.strip() in ("TikTok Channel", "TikTok", "Log In", "Đăng nhập"):
                channel_name = get_tiktok_fallback(final_url)
    except Exception as e:
        logger.error(f"Playwright TikTok channel info failed: {e}")
        channel_name = get_tiktok_fallback(url)
    finally:
        if browser:
            await browser.close()
            
    return channel_name.strip(), channel_id.strip()

async def scrape_facebook_channel_info(url: str) -> tuple[str, str]:
    """
    Extracts Facebook page/profile name and ID using Playwright.
    """
    logger.info(f"Playwright: Extracting Facebook channel info for {url}")
    channel_name = "Facebook Page"
    
    parsed_id = url.rstrip('/').split('/')[-1]
    if 'profile.php' in url and 'id=' in url:
        match = re.search(r'id=(\d+)', url)
        if match:
            parsed_id = match.group(1)
    channel_id = parsed_id
    
    browser = None
    try:
        async with async_playwright() as p:
            browser, page = await _launch_stealth_browser(p, platform='facebook')
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            
            final_url = page.url
            if 'profile.php' in final_url and 'id=' in final_url:
                match = re.search(r'id=(\d+)', final_url)
                if match:
                    channel_id = match.group(1)
            else:
                p_id = final_url.rstrip('/').split('/')[-1].split('?')[0]
                if p_id and p_id not in ('posts', 'videos', 'reels', 'photos', 'about', 'reviews'):
                    channel_id = p_id
            
            # Dismiss popup
            try:
                close_btn = await page.query_selector('div[role="dialog"] div[aria-label="Đóng"], div[role="dialog"] div[aria-label="Close"]')
                if close_btn:
                    await close_btn.click()
            except Exception:
                pass
                
            h1_el = await page.query_selector('h1')
            if h1_el:
                channel_name = await h1_el.inner_text()
            else:
                page_title = await page.title()
                if page_title and page_title.strip() not in ("Facebook", "Log In", "Đăng nhập"):
                    channel_name = page_title.split('|')[0].strip()
                    
            if not channel_name or channel_name.strip() in ("Facebook Page", "Facebook", "Log In", "Đăng nhập"):
                channel_name = get_facebook_fallback(final_url)
    except Exception as e:
        logger.error(f"Playwright Facebook channel info failed: {e}")
        channel_name = get_facebook_fallback(url)
    finally:
        if browser:
            await browser.close()
            
    return channel_name.strip(), channel_id.strip()
