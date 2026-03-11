# main.py — MailSift Python Scanner API

import asyncio
import logging
import os
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="MailSift Scanner API")

# CORS — allow your Vercel domain + localhost dev
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

MAX_CONCURRENCY = 5
TIMEOUT         = 8000

USER_SELECTORS = [
    'input[type="email"]',
    'input[type="text"][name*="user" i]',
    'input[name*="login" i]',
    'input[name*="email" i]',
    'input[id*="user" i]',
    'input[id*="email" i]',
    'input[id*="login" i]',
]

PASS_SELECTORS = [
    'input[type="password"]',
    'input[name*="pass" i]',
    'input[id*="pass" i]',
]

class ScanRequest(BaseModel):
    emails: List[str]
    mode:   Literal["webmail", "mail", "both"] = "webmail"

class EmailResult(BaseModel):
    email:      str
    hasWebmail: bool
    webmailUrl: Optional[str] = None
    hasMail:    bool
    mailUrl:    Optional[str] = None

class ScanResponse(BaseModel):
    results: List[EmailResult]

async def check_url(url: str, playwright) -> bool:
    browser = None
    try:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        response = await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT)

        if not response or response.status != 200:
            return False

        final_url     = page.url
        parsed_final  = urlparse(final_url)
        parsed_origin = urlparse(url)

        if parsed_final.netloc != parsed_origin.netloc:
            return False

        if ":2096" in final_url or "roundcube" in final_url.lower():
            return False

        user_found = False
        for selector in USER_SELECTORS:
            if await page.locator(selector).count() > 0:
                user_found = True
                break

        pass_found = False
        for selector in PASS_SELECTORS:
            if await page.locator(selector).count() > 0:
                pass_found = True
                break

        return user_found and pass_found

    except PlaywrightTimeoutError:
        return False
    except Exception as e:
        logging.debug(f"Error checking {url}: {e}")
        return False
    finally:
        if browser:
            await browser.close()


async def check_domain(domain: str, mode: str, semaphore: asyncio.Semaphore, playwright) -> dict:
    webmail_url = f"https://webmail.{domain}/"
    mail_url    = f"https://mail.{domain}/"
    webmail_hit = False
    mail_hit    = False

    async with semaphore:
        if mode == "webmail":
            webmail_hit = await check_url(webmail_url, playwright)
        elif mode == "mail":
            mail_hit = await check_url(mail_url, playwright)
        elif mode == "both":
            results     = await asyncio.gather(
                check_url(webmail_url, playwright),
                check_url(mail_url, playwright),
            )
            webmail_hit = results[0]
            mail_hit    = results[1]

    return {
        "domain":     domain,
        "webmailUrl": webmail_url if webmail_hit else None,
        "mailUrl":    mail_url    if mail_hit    else None,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "MailSift Scanner API"}


@app.post("/scan", response_model=ScanResponse)
async def scan_emails(body: ScanRequest):
    if not body.emails:
        raise HTTPException(status_code=400, detail="No emails provided")

    if len(body.emails) > 5000:
        raise HTTPException(status_code=400, detail="Max 5000 emails per request")

    domain_map: dict[str, list[str]] = {}
    for email in body.emails:
        email = email.strip()
        parts = email.split("@")
        if len(parts) != 2:
            continue
        domain = parts[1].lower().strip()
        if not domain:
            continue
        domain_map.setdefault(domain, []).append(email)

    domains   = list(domain_map.keys())
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    results: list[EmailResult] = []

    async with async_playwright() as playwright:
        tasks = [check_domain(d, body.mode, semaphore, playwright) for d in domains]
        domain_results = await asyncio.gather(*tasks)

        for dr in domain_results:
            for email in domain_map.get(dr["domain"], []):
                results.append(EmailResult(
                    email      = email,
                    hasWebmail = dr["webmailUrl"] is not None,
                    webmailUrl = dr["webmailUrl"],
                    hasMail    = dr["mailUrl"] is not None,
                    mailUrl    = dr["mailUrl"],
                ))

    return ScanResponse(results=results)