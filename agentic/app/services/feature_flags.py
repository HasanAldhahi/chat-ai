"""Feature flag service for agentic layer (Task 5.4 UAT)."""

import os
from typing import Optional

from pydantic_settings import BaseSettings


class FeatureFlags(BaseSettings):
    """Feature flags for agentic layer.

    All flags can be overridden via environment variables.
    """

    # AGENTIC_BETA_BANNER: Show "BETA" banner in UI
    # When enabled, displays a prominent banner indicating the agentic layer
    # is in beta testing. This is required for UAT cohorts to set user expectations.
    AGENTIC_BETA_BANNER: bool = True

    # AGENTIC_UAT_ENABLED: Enable UAT-specific behavior
    # When enabled, includes additional logging and diagnostics for UAT testing.
    AGENTIC_UAT_ENABLED: bool = os.getenv("AGENTIC_UAT_ENV", "development") != "production"

    # AGENTIC_MULTIMODAL_ENABLED: Enable multimodal AI capabilities
    AGENTIC_MULTIMODAL_ENABLED: bool = False

    # AGENTIC_TOOLS_LANDING_PAGE: Enable tools landing page
    AGENTIC_TOOLS_LANDING_PAGE_ENABLED: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global feature flags instance
_feature_flags: Optional[FeatureFlags] = None


def get_feature_flags() -> FeatureFlags:
    """Get the global feature flags instance.

    Returns:
        FeatureFlags: The feature flags instance.
    """
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags()
    return _feature_flags