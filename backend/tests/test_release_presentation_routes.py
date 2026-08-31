from app.main import app


def test_registered_release_presentation_routes_exclude_retired_authority_paths():
    paths = {route.path for route in app.routes}

    assert "/api/v1/health" in paths
    assert "/api/v1/alert-triage/clusters" in paths
    assert "/api/v1/investigations/{investigation_id}/intelligence/reconstruction" in paths
    assert "/api/v1/investigations/{investigation_id}/findings" in paths
    assert "/api/v1/investigations/{investigation_id}/mitre" in paths
    assert "/api/v1/investigations/{investigation_id}/notes" in paths
    assert "/api/v1/investigations/{investigation_id}/audit" in paths
    assert not any(path.endswith("/analyze") for path in paths)
    assert not any("intelligence/items/{item_id}/finding" in path for path in paths)
    assert not any("claim" in path and "finding" in path for path in paths)
