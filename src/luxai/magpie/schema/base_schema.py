"""Transport-independent RPC schema contract."""


class BaseSchema:
    def dispatch(self, request_obj):
        raise NotImplementedError

    def wrap(self, method, params=None):
        raise NotImplementedError

    def unwrap(self, response):
        raise NotImplementedError

