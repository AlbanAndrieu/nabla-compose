"""Non-invasive DAST: limit ZAP requests before the packaged spider starts.

The ZAP Network add-on is required. Fail closed when rate limiting cannot be
enabled, rather than accidentally flooding Vercel or masking WAF challenges.
Never log URLs, cookies, request bodies, tokens or full scan evidence.
"""

from urllib.parse import urlsplit

MAX_RPS = "1"


def zap_started(zap, target):
    parsed = urlsplit(target)
    host = parsed.hostname
    if parsed.scheme != "https" or not host:
        raise RuntimeError("ZAP_THROTTLE_INVALID_TARGET")
    if host != "www.albanandrieu.com" and not (
        host.endswith(".vercel.app") and host != "vercel.app"
    ):
        raise RuntimeError("ZAP_THROTTLE_OUT_OF_SCOPE")
    # Production may 308/301 from www to the apex. One shared rule prevents
    # redirected requests from escaping the rate budget.
    is_production = host == "www.albanandrieu.com"
    matchstring = r"^(?:www\.)?albanandrieu\.com$" if is_production else host
    response = zap.network.add_rate_limit_rule(
        description="alban-ci-1rps",
        enabled="true",
        matchregex="true" if is_production else "false",
        matchstring=matchstring,
        requestspersecond=MAX_RPS,
        groupby="rule",
    )
    if str(response).strip().lower() != "ok":
        raise RuntimeError("ZAP_THROTTLE_NOT_ENABLED")
    return zap, target

def zap_pre_shutdown(zap):
    """Produce PLUS evidence while the ZAP daemon still holds HTTP messages.

    Standard -x/-J/-r reports are preserved as fallbacks, but native
    report-full.xml is the authoritative input for DefectDojo.
    """
    for template, filename in (
        ("traditional-xml-plus", "report-full.xml"),
        ("traditional-json-plus", "report-full.json"),
        ("traditional-html-plus", "report-full.html"),
    ):
        result = zap.reports.generate(
            title="Site Alban private DAST full evidence",
            template=template,
            reportfilename=filename,
            reportdir="/zap/wrk",
            display="false",
        )
        if not result:
            raise RuntimeError("ZAP_FULL_REPORT_NOT_GENERATED")
