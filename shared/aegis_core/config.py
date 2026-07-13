"""Environment-driven configuration shared by all services."""

import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    env: str = "dev"
    aws_region: str = "us-east-1"
    service_name: str = "unknown"


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings(
        env=os.environ.get("AEGIS_ENV", "dev"),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        service_name=os.environ.get("AEGIS_SERVICE", "unknown"),
    )
