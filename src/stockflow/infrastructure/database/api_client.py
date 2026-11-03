"""Supabase client bound to one verified API access token."""

import os

from dotenv import load_dotenv

from stockflow.infrastructure.database.supabase_client import KEY_VAR, URL_VAR


class InvalidAccessToken(Exception):
    """The supplied Supabase access token is missing, invalid, or expired."""


def create_authenticated_client(access_token: str):
    load_dotenv()
    url, key = os.environ.get(URL_VAR), os.environ.get(KEY_VAR)
    if not (url and key):
        raise RuntimeError(
            f"Defina {URL_VAR} e {KEY_VAR} no .env para usar a API."
        )

    from supabase import AuthApiError, ClientOptions, create_client

    client = create_client(
        url,
        key,
        options=ClientOptions(
            persist_session=False,
            auto_refresh_token=False,
        ),
    )
    try:
        user = client.auth.get_user(access_token).user
    except AuthApiError as error:
        if error.status not in {400, 401, 403}:
            raise
        raise InvalidAccessToken from error
    if user is None:
        raise InvalidAccessToken

    client.postgrest.auth(access_token)
    return client
