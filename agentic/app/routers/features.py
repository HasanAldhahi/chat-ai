"""Feature flags API router (Task 5.4 UAT)."""

from fastapi import APIRouter, Depends

from app.services.feature_flags import FeatureFlags, get_feature_flags

router = APIRouter(prefix="/api/agent/config", tags=["features"])


@router.get("/features")
async def get_features(
    flags: FeatureFlags = Depends(get_feature_flags),
) -> dict:
    """Get current feature flags for the client.

    This endpoint is intentionally unauthenticated so the frontend can
    retrieve feature configuration at startup.

    Returns:
        dict: Key-value pairs of feature flags.
    """
    return {
        "betaBanner": flags.AGENTIC_BETA_BANNER,
        "uatEnabled": flags.AGENTIC_UAT_ENABLED,
        "multimodalEnabled": flags.AGENTIC_MULTIMODAL_ENABLED,
        "toolsLandingPageEnabled": flags.AGENTIC_TOOLS_LANDING_PAGE_ENABLED,
    }