"""Dynatrace RUM (Real User Monitoring) JavaScript tag injection.

Dynatrace Frontend(Web) application의 "Agentless" JavaScript tag를 서버에서
HTML <head> 맨 앞에 직접 삽입한다. (OneAgent 자동 주입이 동작하는 환경이라면
DT_RUM_SNIPPET을 비워 이중 삽입을 피한다)

JavaScript tag를 얻는 방법 (우선순위 순):
  1. DT_RUM_SNIPPET  (env) / rum-snippet  (secret)  : 테넌트에서 복사한 <script ...></script> 전체
  2. DT_RUM_APP_ID   (env) / rum-app-id   (secret)  : 앱 기동 시 Dynatrace API로 최신 tag를 조회
       GET {tenant}/api/v2/rum/javaScriptTag/{applicationId}
       토큰 scope: rumManualInsertionTags.read
     tenant URL은 DT_ENDPOINT(env) 또는 secret endpoint에서 추출한다. (classic APPLICATION- ID 전용)
둘 다 없으면 주입하지 않는다(기존 동작과 동일).
"""

import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from utils.secrets import read_secret

logger = logging.getLogger(__name__)

# <head> 와 바로 뒤따르는 <meta charset>/<meta http-equiv> 까지 매치 → 그 다음에 tag 삽입
_HEAD_OPEN = re.compile(
    r"<head(?:\s[^>]*)?>(?:\s*<meta\s[^>]*(?:charset|http-equiv)[^>]*>)*",
    re.IGNORECASE,
)


def _setting(env_name: str, secret_name: str) -> str:
    value = os.environ.get(env_name)
    if value is None:
        value = read_secret(secret_name)
    return (value or "").strip()


def _tenant_url(otlp_endpoint: str) -> str:
    """https://abc12345.live.dynatrace.com/api/v2/otlp -> https://abc12345.live.dynatrace.com"""
    base = os.environ.get("DT_ENDPOINT", "").strip() or otlp_endpoint.strip()
    idx = base.find("/api/")
    if idx != -1:
        base = base[:idx]
    return base.rstrip("/")


def _fetch_js_tag(tenant: str, app_id: str, token: str) -> str:
    query = urllib.parse.urlencode(
        {
            # Dynatrace 권장: 동기 로딩(NONE)이 가장 이른 시점부터 수집. 필요 시 ASYNC/DEFER로 변경
            "scriptExecutionAttribute": os.environ.get("DT_RUM_SCRIPT_EXECUTION", "NONE"),
            "crossOriginAnonymous": "true",
        }
    )
    url = f"{tenant}/api/v2/rum/javaScriptTag/{urllib.parse.quote(app_id)}?{query}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Api-Token {token}", "Accept": "text/plain"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8").strip()


def load_rum_snippet(otlp_endpoint: str, token: str) -> str:
    snippet = _setting("DT_RUM_SNIPPET", "rum-snippet")
    if snippet:
        logger.info("Dynatrace RUM: using JavaScript tag from DT_RUM_SNIPPET / rum-snippet")
        return snippet

    app_id = _setting("DT_RUM_APP_ID", "rum-app-id")
    if not app_id:
        logger.info("Dynatrace RUM: disabled (DT_RUM_SNIPPET / DT_RUM_APP_ID not set)")
        return ""

    tenant = _tenant_url(otlp_endpoint)
    if not tenant or not token:
        logger.warning("Dynatrace RUM: DT_RUM_APP_ID set but tenant URL or API token missing")
        return ""

    try:
        snippet = _fetch_js_tag(tenant, app_id, token)
    except urllib.error.HTTPError as e:
        # 401/403 이면 토큰에 rumManualInsertionTags.read scope가 없는 경우가 대부분
        logger.warning(f"Dynatrace RUM: JavaScript tag API returned HTTP {e.code} for {app_id}")
        return ""
    except Exception as e:
        logger.warning(f"Dynatrace RUM: failed to fetch JavaScript tag for {app_id}: {e}")
        return ""

    if "<script" not in snippet.lower():
        logger.warning("Dynatrace RUM: unexpected JavaScript tag response, injection skipped")
        return ""
    logger.info(f"Dynatrace RUM: JavaScript tag loaded from {tenant} for {app_id}")
    return snippet


def inject_snippet(html: str, snippet: str) -> str:
    """RUM tag는 다른 스크립트보다 먼저 로드돼야 하므로 <head>의 charset/http-equiv meta 바로 뒤, 첫 스크립트로 넣는다."""
    if not snippet or snippet in html:
        return html
    m = _HEAD_OPEN.search(html)
    if not m:
        return snippet + html
    return html[: m.end()] + "\n" + snippet + html[m.end():]
