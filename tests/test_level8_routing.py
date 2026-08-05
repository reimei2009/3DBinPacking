from __future__ import annotations

import json
from pathlib import Path

import pytest

from container_packing.application.service import get_instance_limits
from container_packing.data_loader import load_config
from container_packing.levels.level_08_routing import (
    DeclaredOrderOfflineProvider,
    GoogleRoutesProvider,
    load_delivery_stops,
    ordered_route_stops,
    validate_item_stop_references,
    validate_optional_routing_artifacts,
    write_optional_routing_artifacts,
)
from container_packing.levels.pipeline import ValidationBundle
from container_packing.schemas import Item, ValidationResult


def _item(item_id: str, priority: int, stop_id: str) -> Item:
    return Item(
        item_id,
        10,
        10,
        10,
        1,
        source={
            "delivery_priority": str(priority),
            "delivery_stop_id": stop_id,
            "delivery_data_source": "test",
        },
    )


def _config(stops_file: Path, provider: str = "offline") -> dict:
    return {
        "routing": {
            "enabled": True,
            "provider": provider,
            "stops_file": str(stops_file),
            "travel_mode": "DRIVE",
            "return_to_depot": False,
            "timeout_seconds": 2,
            "fallback_to_offline": True,
        }
    }


def test_stop_contract_and_declared_order_are_deterministic(root: Path) -> None:
    stops = load_delivery_stops(
        root / "data/raw/level_08/routes/web_three_stop_route.csv"
    )
    ordered = ordered_route_stops(stops, return_to_depot=False)
    provider = DeclaredOrderOfflineProvider()
    first = provider.compute(
        stops, travel_mode="DRIVE", return_to_depot=False, timeout_seconds=1
    )
    second = provider.compute(
        stops, travel_mode="DRIVE", return_to_depot=False, timeout_seconds=1
    )

    assert [stop.stop_id for stop in ordered] == [
        "DEPOT",
        "STOP-A",
        "STOP-B",
        "STOP-C",
    ]
    assert first == second
    assert first.total_distance_meters > 0
    assert first.total_duration_seconds > 0


def test_web_profile_registry_uses_tracked_reproducible_sources(
    root: Path,
) -> None:
    registry = load_config(root / "config/level_08/web_profiles.yaml")
    comparable = registry["profiles"]["comparable"]
    research = registry["profiles"]["research"]
    comparable_limits = get_instance_limits(comparable["config_file"], root=root)
    limits = get_instance_limits(research["config_file"], root=root)
    manifest = json.loads(
        (
            root
            / "data/raw/level_08/web_demo/level_08_web_demo_100_c10_v1_manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert tuple(registry["profiles"]) == (
        "quick", "standard", "comparable", "research"
    )
    assert comparable["cross_level_comparable"] is True
    assert comparable_limits.available_items == 501
    assert comparable_limits.configured_containers == 10
    assert limits.available_items == 100
    assert limits.configured_containers == 10
    assert manifest["item_count"] == 100
    assert manifest["container_count"] == 10
    assert manifest["delivery_stop_count"] == 5


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "stop_id,stop_type,delivery_priority,name,latitude,longitude\n"
            "A,delivery,1,A,10,106\n",
            "exactly one depot",
        ),
        (
            "stop_id,stop_type,delivery_priority,name,latitude,longitude\n"
            "D,depot,,D,10,106\nA,delivery,1,A,91,106\n",
            "latitude",
        ),
        (
            "stop_id,stop_type,delivery_priority,name,latitude,longitude\n"
            "D,depot,,D,10,106\nA,delivery,1,A,10,106\n"
            "B,delivery,1,B,11,107\n",
            "priorities must be unique",
        ),
    ],
)
def test_stop_contract_rejects_invalid_csv(
    tmp_path: Path, body: str, message: str
) -> None:
    path = tmp_path / "stops.csv"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_delivery_stops(path)


def test_item_stop_references_must_resolve(root: Path) -> None:
    stops = load_delivery_stops(
        root / "data/raw/level_08/routes/web_three_stop_route.csv"
    )
    validate_item_stop_references([_item("A", 1, "STOP-A")], stops)
    with pytest.raises(ValueError, match="unknown delivery stops"):
        validate_item_stop_references([_item("A", 1, "UNKNOWN")], stops)
    with pytest.raises(ValueError, match="priorities disagree"):
        validate_item_stop_references([_item("A", 2, "STOP-A")], stops)


def test_google_provider_uses_field_mask_and_never_passes_key_in_payload(
    root: Path,
) -> None:
    stops = load_delivery_stops(
        root / "data/raw/level_08/routes/web_three_stop_route.csv"
    )
    captured: dict = {}

    def transport(url, headers, payload, timeout):
        captured.update(
            {"url": url, "headers": headers, "payload": payload, "timeout": timeout}
        )
        return {
            "diagnostic": "secret-value",
            "routes": [
                {
                    "distanceMeters": 3000,
                    "duration": "600s",
                    "legs": [
                        {"distanceMeters": 1000, "duration": "200s"},
                        {"distanceMeters": 1000, "duration": "200s"},
                        {"distanceMeters": 1000, "duration": "200s"},
                    ],
                    "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                }
            ]
        }

    result = GoogleRoutesProvider("secret-value", transport=transport).compute(
        stops, travel_mode="DRIVE", return_to_depot=False, timeout_seconds=3
    )

    assert result.provider_used == "google_routes"
    assert result.total_distance_meters == 3000
    assert captured["headers"]["X-Goog-Api-Key"] == "secret-value"
    assert "routes.polyline.encodedPolyline" in captured["headers"]["X-Goog-FieldMask"]
    assert "secret-value" not in json.dumps(captured["payload"])
    assert "secret-value" not in json.dumps(result.response_snapshot)
    assert result.response_snapshot["diagnostic"] == "[REDACTED]"
    assert result.request_snapshot.get("api_key") is None


def test_missing_google_key_falls_back_and_artifacts_revalidate(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOOGLE_ROUTES_API_KEY", raising=False)
    source = root / "data/raw/level_08/routes/web_three_stop_route.csv"
    run_dir = tmp_path / "run"
    (run_dir / "metrics").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"artifacts": {"derived": []}}), encoding="utf-8"
    )
    (run_dir / "metrics/metrics.json").write_text("{}", encoding="utf-8")
    items = [
        _item("A", 1, "STOP-A"),
        _item("B", 2, "STOP-B"),
        _item("C", 3, "STOP-C"),
    ]
    config = _config(source, provider="google_routes")
    metadata: dict = {}

    write_optional_routing_artifacts(
        run_dir,
        items,
        config,
        metadata,
        ValidationBundle(ValidationResult(True, [])),
    )
    validation = validate_optional_routing_artifacts(
        run_dir, items, config, packing_valid=True
    )
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (run_dir / "routing").iterdir()
        if path.is_file()
    )

    assert validation.valid
    assert metadata["routing_provider_used"] == "offline"
    assert metadata["routing_fallback_used"] is True
    assert "secret-value" not in persisted


def test_routing_artifact_tampering_is_detected(
    root: Path, tmp_path: Path
) -> None:
    source = root / "data/raw/level_08/routes/web_three_stop_route.csv"
    run_dir = tmp_path / "run"
    (run_dir / "metrics").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"artifacts": {"derived": []}}), encoding="utf-8"
    )
    (run_dir / "metrics/metrics.json").write_text("{}", encoding="utf-8")
    items = [
        _item("A", 1, "STOP-A"),
        _item("B", 2, "STOP-B"),
        _item("C", 3, "STOP-C"),
    ]
    config = _config(source)
    write_optional_routing_artifacts(
        run_dir,
        items,
        config,
        {},
        ValidationBundle(ValidationResult(True, [])),
    )
    (run_dir / "routing/route.json").write_text("{}", encoding="utf-8")

    validation = validate_optional_routing_artifacts(
        run_dir, items, config, packing_valid=True
    )

    assert not validation.valid
    assert validation.issues[0].code == "ROUTING_ARTIFACT_INVALID"
