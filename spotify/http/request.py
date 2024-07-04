import json
import atexit
import requests
from tls_client import Session
from typing import Any, Callable, Type, Union
from tls_client.exceptions import TLSClientExeption
from tls_client.response import Response as TLSResponse
from spotify.http.types import Response
from spotify.exceptions import ParentException


class StdClient(requests.Session):
    def __init__(
        self, auto_retries: int = 0, auth_rule: Callable[[dict[Any, Any]], dict] = None
    ) -> None:
        super().__init__()
        self.auto_retries = auto_retries + 1
        self.authenticate = auth_rule
        atexit.register(self.close)

    def __call__(
        self, method: str, url: str, **kwargs
    ) -> Union[requests.Response, None]:
        return self.build_request(method, url, kwargs)

    def build_request(
        self, method: str, url: str, **kwargs
    ) -> Union[requests.Response, None]:
        for _ in range(self.auto_retries):
            try:
                response = super().request(method.upper(), url, **kwargs)
            except Exception:
                continue
            else:
                return response
        return

    def parse_response(self, response: requests.Response) -> Response:
        body: Union[str, dict, None] = response.text
        headers = {key.lower(): value for key, value in response.headers.items()}

        if "application/json" in headers.get("content-type", ""):
            try:
                body = response.json()
            except ValueError:
                pass

        return Response(status_code=response.status_code, response=body, raw=response)

    def request(
        self, method: str, url: str, *, authenticate: bool = False, **kwargs
    ) -> Union[Response, None]:
        if authenticate and self.authenticate:
            kwargs = self.authenticate(kwargs)

        response = self.build_request(method, url, **kwargs)

        if response is not None:
            return self.parse_response(response)

    def post(
        self, url: str, *, authenticate: bool = False, **kwargs
    ) -> Union[Response, None]:
        return self.request("POST", url, authenticate=authenticate, **kwargs)

    def get(
        self, url: str, *, authenticate: bool = False, **kwargs
    ) -> Union[Response, None]:
        return self.request("GET", url, authenticate=authenticate, **kwargs)


class TLSClient(Session):
    def __init__(
        self,
        profile: str,
        proxy: str,
        *,
        auto_retries: int = 0,
        auth_rule: Callable[[dict[Any, Any]], dict] = None,
    ) -> None:
        super().__init__(client_identifier=profile, random_tls_extension_order=True)

        if proxy:
            self.proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

        self.auto_retries = auto_retries + 1
        self.authenticate = auth_rule
        self.fail_exception: Type[ParentException] = None
        atexit.register(self.close)

    def __call__(self, method: str, url: str, **kwargs) -> Union[TLSResponse, None]:
        return self.build_request(method, url, kwargs)

    def build_request(
        self, method: str, url: str, **kwargs
    ) -> Union[TLSResponse, None]:
        for _ in range(self.auto_retries):
            try:
                response = self.execute_request(method.upper(), url, **kwargs)
            except TLSClientExeption as err:
                # TODO: Display error
                continue
            else:
                return response

        return

    def parse_response(
        self, response: TLSResponse, method: str, danger: bool
    ) -> Response:
        body: Union[str, dict, None] = response.text
        headers = {key.lower(): value for key, value in response.headers.items()}

        # Spotify doesn't set content-type for some reason?
        json_encoded = "application/json" in headers.get("content-type", "")
        is_dict = True

        try:
            json.loads(body)
        except json.JSONDecodeError:
            is_dict = False

        if json_encoded or is_dict:
            json_formatted = response.json()
            body = json_formatted if isinstance(json_formatted, dict) else body

        if not body:
            body = None

        resp = Response(status_code=response.status_code, response=body, raw=response)

        if danger and self.fail_exception and resp.fail:
            raise self.fail_exception(
                f"Could not {method} {str(response.url).split('?')[0]}. Status Code: {resp.status_code}",
                "Request Failed.",
            )

        return resp

    def get(
        self, url: str, *, authenticate: bool = False, **kwargs
    ) -> Union[Response, None]:
        """Routes a GET Request"""
        if authenticate:
            kwargs = self.authenticate(kwargs)

        response = self.build_request("GET", url, **kwargs)

        if response is None:
            return

        return self.parse_response(response, "GET", True)

    def post(
        self, url: str, *, authenticate: bool = False, danger: bool = False, **kwargs
    ) -> Union[Response, None]:
        """Routes a POST Request"""
        if authenticate:
            kwargs = self.authenticate(kwargs)

        response = self.build_request("POST", url, **kwargs)

        if response is None:
            return

        return self.parse_response(response, "POST", danger)
