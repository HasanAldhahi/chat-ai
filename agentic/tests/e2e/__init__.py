"""Phase 5 / Task 5.2 end-to-end test suite.

One module per user story (US-001..US-009 in `spec.md`). Each module
drives the *integrated* broker + MCP path with the same FastAPI
TestClient the broker is deployed under, while Slurm / Vault / vLLM
upstream are pinned to their mock or `httpx.MockTransport` doubles.

Tests here are tagged ``@pytest.mark.e2e`` so they can be run as a CI
gate via:

    pytest agentic/tests/e2e/ -m e2e
"""
