"""Who owns a correspondent we create, and how it matches (#50).

Paperless hands a new object to the token's user unless the request says
otherwise, so everything Paperless-AIssist created belonged to the API user and
nobody else could see it. Both settings are opt-in: at their defaults the POST
body is exactly what it always was, just the name.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.paperless import PaperlessClient
from app.services.steps.correspondent_step import CorrespondentStep

BASE_URL = "http://paperless.test"


def _client_with_no_match():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    listing = MagicMock()
    listing.raise_for_status = MagicMock()
    listing.json.return_value = {"count": 0, "next": None, "results": []}
    client.client.get = AsyncMock(return_value=listing)
    created = MagicMock()
    created.raise_for_status = MagicMock()
    created.json.return_value = {"id": 7, "name": "Telekom"}
    client.client.post = AsyncMock(return_value=created)
    return client


class TestTheClientSendsWhatWasAsked:
    @pytest.mark.asyncio
    async def test_the_default_body_is_unchanged(self):
        """Verified live against Paperless 3.0.5: omitting owner makes the API
        user the owner. Leaving the setting alone must keep that exact body."""
        client = _client_with_no_match()

        await client.get_or_create_correspondent("Telekom")

        assert client.client.post.await_args.kwargs["json"] == {"name": "Telekom"}
        await client.close()

    @pytest.mark.asyncio
    async def test_nobody_sends_an_explicit_null_owner(self):
        """Verified live: "owner": null creates an unowned, visible-to-all object."""
        client = _client_with_no_match()

        await client.get_or_create_correspondent("Telekom", owner_mode="none")

        body = client.client.post.await_args.kwargs["json"]
        assert "owner" in body and body["owner"] is None
        await client.close()

    @pytest.mark.asyncio
    async def test_a_matching_algorithm_is_sent_only_when_set(self):
        client = _client_with_no_match()

        await client.get_or_create_correspondent("Telekom", matching_algorithm=6)
        assert client.client.post.await_args.kwargs["json"]["matching_algorithm"] == 6

        await client.get_or_create_correspondent("Telekom")
        assert "matching_algorithm" not in client.client.post.await_args.kwargs["json"]
        await client.close()


class TestTheStepReadsTheSettings:
    def test_owner_defaults_to_the_api_user(self):
        assert CorrespondentStep({})._create_owner_mode() == "api_user"
        assert CorrespondentStep({"correspondent_create_owner": "none"})._create_owner_mode() == "none"
        # Anything unexpected falls back to the safe default rather than to "none".
        assert CorrespondentStep({"correspondent_create_owner": "everyone"})._create_owner_mode() == "api_user"

    def test_matching_defaults_to_leaving_paperless_alone(self):
        assert CorrespondentStep({})._create_matching_algorithm() is None
        assert CorrespondentStep({"correspondent_create_matching": "6"})._create_matching_algorithm() == 6
        assert CorrespondentStep({"correspondent_create_matching": "0"})._create_matching_algorithm() == 0
        # Out of range or garbage: leave it to Paperless, never send nonsense.
        assert CorrespondentStep({"correspondent_create_matching": "9"})._create_matching_algorithm() is None
        assert CorrespondentStep({"correspondent_create_matching": "fast"})._create_matching_algorithm() is None
