"""Cooperative collection cancellation; never abort an in-flight platform request."""
class CollectionStopped(Exception):
    pass


def checkpoint(should_stop):
    if should_stop and should_stop():
        raise CollectionStopped('已停止后续请求')


class CollectionAccessLimited(CollectionStopped):
    pass


def access_limited(exc):
    message = str(exc).lower()
    return any(t in message for t in ('429', '403', '验证码', '频繁', '风控', '登录失效', 'captcha', 'rate limit', 'unauthorized'))
