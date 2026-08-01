import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_timezone_is_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(app_timezone="Not/A_Timezone")


def test_log_level_is_normalized() -> None:
    assert Settings(log_level="warning").log_level == "WARNING"
