from importlib import import_module


auth_router_module = import_module("src.auth.router")


def test_auth_rate_limit_defaults_match_browser_workload():
    assert auth_router_module.LOGIN_RATE_LIMIT == "60/minute"
    assert auth_router_module.FORGOT_PASSWORD_RATE_LIMIT == "5/hour"
    assert auth_router_module.RESET_PASSWORD_RATE_LIMIT == "5/minute"
