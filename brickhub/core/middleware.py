CSP = "; ".join([
    "default-src 'self'",
    "img-src 'self' data: blob: https:",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self' https://www.liqpay.ua",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])


class SecurityHeadersMiddleware:
    """Content-Security-Policy and Permissions-Policy for every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        if request.path.startswith(("/panel/", "/kabinet/", "/django-admin/", "/koshyk/", "/zamovlennia/")):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response
