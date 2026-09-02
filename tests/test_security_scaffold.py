import pytest
from fastapi import HTTPException

from app.core.security import get_current_admin, get_current_student, parse_bearer_token


def test_parse_bearer_token_valid() -> None:
    parsed = parse_bearer_token("Bearer 42|sometoken")
    assert parsed.token_id == "42"
    assert parsed.plaintext == "sometoken"


@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer", "Bearer no-pipe-here", "Bearer 42|"],
)
def test_parse_bearer_token_rejects_malformed(header: str | None) -> None:
    with pytest.raises(HTTPException) as exc_info:
        parse_bearer_token(header)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_guard_not_yet_implemented() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_admin(authorization="Bearer 1|abc")
    assert exc_info.value.status_code == 501


@pytest.mark.asyncio
async def test_student_guard_not_yet_implemented() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_student(authorization="Bearer 1|abc")
    assert exc_info.value.status_code == 501
