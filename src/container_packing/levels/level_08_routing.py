"""Optional Level 8 route enrichment over a declared delivery-stop order.

Routing is deliberately downstream of packing and validation.  It never
changes placements, delivery priorities, the solver objective, or the Level
1--8 validation result.
"""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from ..provenance import sha256_file
from ..runtime.project import find_project_root
from ..schemas import Item, ValidationIssue, ValidationResult
from .pipeline import ValidationBundle
from .unloading import delivery_attributes_for_item

ROUTING_SCHEMA_VERSION = "1.0"
GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_FIELD_MASK = (
    "routes.distanceMeters,routes.duration,routes.legs.distanceMeters,"
    "routes.legs.duration,routes.polyline.encodedPolyline"
)
STOP_COLUMNS = (
    "stop_id",
    "stop_type",
    "delivery_priority",
    "name",
    "latitude",
    "longitude",
    "address",
    "service_duration_seconds",
    "data_source",
)


@dataclass(frozen=True)
class DeliveryStop:
    stop_id: str
    stop_type: str
    delivery_priority: int | None
    name: str
    latitude: float
    longitude: float
    address: str
    service_duration_seconds: float
    data_source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteLeg:
    sequence: int
    origin_stop_id: str
    destination_stop_id: str
    distance_meters: float
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteResult:
    provider_requested: str
    provider_used: str
    travel_mode: str
    return_to_depot: bool
    ordered_stop_ids: tuple[str, ...]
    legs: tuple[RouteLeg, ...]
    polyline_coordinates: tuple[tuple[float, float], ...]
    total_distance_meters: float
    total_duration_seconds: float
    request_snapshot: dict[str, Any]
    response_snapshot: dict[str, Any]
    warning: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": ROUTING_SCHEMA_VERSION,
            "provider_requested": self.provider_requested,
            "provider_used": self.provider_used,
            "travel_mode": self.travel_mode,
            "return_to_depot": self.return_to_depot,
            "ordered_stop_ids": list(self.ordered_stop_ids),
            "legs": [value.to_dict() for value in self.legs],
            "polyline_coordinates": [
                {"latitude": latitude, "longitude": longitude}
                for latitude, longitude in self.polyline_coordinates
            ],
            "total_distance_meters": self.total_distance_meters,
            "total_duration_seconds": self.total_duration_seconds,
            "warning": self.warning,
        }


class RouteProvider(Protocol):
    provider_id: str

    def compute(
        self,
        stops: tuple[DeliveryStop, ...],
        *,
        travel_mode: str,
        return_to_depot: bool,
        timeout_seconds: float,
    ) -> RouteResult:
        """Compute route evidence without changing the declared stop order."""


class DeclaredOrderOfflineProvider:
    """Deterministic Haversine route used for local tests and safe fallback."""

    provider_id = "offline"

    def __init__(self, *, assumed_speed_kph: float = 35.0) -> None:
        if assumed_speed_kph <= 0:
            raise ValueError("assumed_speed_kph must be positive")
        self.assumed_speed_kph = float(assumed_speed_kph)

    def compute(
        self,
        stops: tuple[DeliveryStop, ...],
        *,
        travel_mode: str,
        return_to_depot: bool,
        timeout_seconds: float,
    ) -> RouteResult:
        del timeout_seconds
        ordered = ordered_route_stops(stops, return_to_depot=return_to_depot)
        legs: list[RouteLeg] = []
        for sequence, (origin, destination) in enumerate(
            zip(ordered, ordered[1:]), start=1
        ):
            distance = _haversine_meters(origin, destination)
            duration = distance / (self.assumed_speed_kph * 1000.0 / 3600.0)
            legs.append(
                RouteLeg(
                    sequence,
                    origin.stop_id,
                    destination.stop_id,
                    distance,
                    duration,
                )
            )
        coordinates = tuple((stop.latitude, stop.longitude) for stop in ordered)
        return RouteResult(
            provider_requested=self.provider_id,
            provider_used=self.provider_id,
            travel_mode=travel_mode,
            return_to_depot=return_to_depot,
            ordered_stop_ids=tuple(stop.stop_id for stop in ordered),
            legs=tuple(legs),
            polyline_coordinates=coordinates,
            total_distance_meters=sum(value.distance_meters for value in legs),
            total_duration_seconds=sum(value.duration_seconds for value in legs),
            request_snapshot={
                "provider": self.provider_id,
                "ordered_stop_ids": [stop.stop_id for stop in ordered],
                "travel_mode": travel_mode,
                "return_to_depot": return_to_depot,
                "distance_model": "haversine",
                "assumed_speed_kph": self.assumed_speed_kph,
            },
            response_snapshot={"model": "deterministic_haversine_v1"},
        )


GoogleTransport = Callable[
    [str, dict[str, str], dict[str, Any], float], dict[str, Any]
]


class GoogleRoutesProvider:
    """Server-side Google Compute Routes adapter with injectable transport."""

    provider_id = "google_routes"

    def __init__(
        self, api_key: str, *, transport: GoogleTransport | None = None
    ) -> None:
        if not api_key.strip():
            raise ValueError("GOOGLE_ROUTES_API_KEY is missing")
        self._api_key = api_key.strip()
        self._transport = transport or _google_transport

    def compute(
        self,
        stops: tuple[DeliveryStop, ...],
        *,
        travel_mode: str,
        return_to_depot: bool,
        timeout_seconds: float,
    ) -> RouteResult:
        ordered = ordered_route_stops(stops, return_to_depot=return_to_depot)
        request_payload = _google_request_payload(ordered, travel_mode)
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": GOOGLE_FIELD_MASK,
        }
        response = self._transport(
            GOOGLE_ROUTES_URL, headers, request_payload, timeout_seconds
        )
        routes = response.get("routes")
        if not isinstance(routes, list) or not routes:
            raise RuntimeError("Google Routes response contains no route")
        route = routes[0]
        raw_legs = route.get("legs")
        if not isinstance(raw_legs, list) or len(raw_legs) != len(ordered) - 1:
            raise RuntimeError("Google Routes response has an unexpected leg count")
        legs = tuple(
            RouteLeg(
                sequence=index,
                origin_stop_id=ordered[index - 1].stop_id,
                destination_stop_id=ordered[index].stop_id,
                distance_meters=float(raw.get("distanceMeters", 0.0)),
                duration_seconds=_duration_seconds(raw.get("duration", "0s")),
            )
            for index, raw in enumerate(raw_legs, start=1)
        )
        encoded = (
            route.get("polyline", {}).get("encodedPolyline")
            if isinstance(route.get("polyline"), dict)
            else None
        )
        coordinates = (
            tuple(_decode_polyline(str(encoded)))
            if encoded
            else tuple((stop.latitude, stop.longitude) for stop in ordered)
        )
        return RouteResult(
            provider_requested=self.provider_id,
            provider_used=self.provider_id,
            travel_mode=travel_mode,
            return_to_depot=return_to_depot,
            ordered_stop_ids=tuple(stop.stop_id for stop in ordered),
            legs=legs,
            polyline_coordinates=coordinates,
            total_distance_meters=float(
                route.get(
                    "distanceMeters",
                    sum(value.distance_meters for value in legs),
                )
            ),
            total_duration_seconds=_duration_seconds(
                route.get(
                    "duration",
                    f"{sum(value.duration_seconds for value in legs)}s",
                )
            ),
            request_snapshot={
                "endpoint": GOOGLE_ROUTES_URL,
                "field_mask": GOOGLE_FIELD_MASK,
                "payload": request_payload,
            },
            response_snapshot=_sanitize_mapping(response, secrets=(self._api_key,)),
        )


def routing_options(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("routing", {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("routing must be a mapping")
    provider = str(value.get("provider", "offline"))
    if provider not in {"offline", "google_routes"}:
        raise ValueError("routing.provider must be offline or google_routes")
    travel_mode = str(value.get("travel_mode", "DRIVE")).upper()
    if travel_mode != "DRIVE":
        raise ValueError("Level 8 logistics demo currently supports travel_mode=DRIVE")
    timeout = float(value.get("timeout_seconds", 10.0))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("routing.timeout_seconds must be a finite positive number")
    stops_file = value.get("stops_file")
    if bool(value.get("enabled", False)) and not isinstance(stops_file, str):
        raise ValueError("routing.stops_file is required when routing is enabled")
    return {
        "enabled": bool(value.get("enabled", False)),
        "provider": provider,
        "stops_file": stops_file,
        "travel_mode": travel_mode,
        "return_to_depot": bool(value.get("return_to_depot", False)),
        "timeout_seconds": timeout,
        "fallback_to_offline": bool(value.get("fallback_to_offline", True)),
        "offline_speed_kph": float(value.get("offline_speed_kph", 35.0)),
    }


def load_delivery_stops(path: str | Path) -> tuple[DeliveryStop, ...]:
    csv_path = Path(path)
    try:
        frame = pd.read_csv(
            csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False
        )
    except (OSError, pd.errors.ParserError) as exc:
        raise ValueError(f"Cannot read delivery stops CSV {csv_path}: {exc}") from exc
    missing = [column for column in STOP_COLUMNS[:6] if column not in frame]
    if missing:
        raise ValueError(
            f"Delivery stops CSV {csv_path} is missing columns: {', '.join(missing)}"
        )
    for optional in STOP_COLUMNS[6:]:
        if optional not in frame:
            frame[optional] = ""
    ids = frame["stop_id"].str.strip()
    if ids.eq("").any():
        raise ValueError("Delivery stop_id must be non-empty")
    duplicates = sorted(ids[ids.duplicated(keep=False)].unique())
    if duplicates:
        raise ValueError("Duplicate delivery stop_id: " + ", ".join(duplicates))
    stops: list[DeliveryStop] = []
    for index, row in frame.iterrows():
        row_number = int(index) + 2
        stop_type = str(row["stop_type"]).strip().lower()
        if stop_type not in {"depot", "delivery"}:
            raise ValueError(
                f"Delivery stops CSV {csv_path}: row {row_number}, "
                "stop_type must be depot or delivery"
            )
        priority_text = str(row["delivery_priority"]).strip()
        if stop_type == "depot":
            if priority_text:
                raise ValueError("Depot delivery_priority must be empty")
            priority = None
        else:
            try:
                priority = int(priority_text)
            except ValueError as exc:
                raise ValueError(
                    f"Delivery stops CSV {csv_path}: row {row_number}, "
                    "delivery_priority must be a positive integer"
                ) from exc
            if priority <= 0 or str(priority) != priority_text:
                raise ValueError(
                    f"Delivery stops CSV {csv_path}: row {row_number}, "
                    "delivery_priority must be a positive integer"
                )
        latitude = _finite_float(
            row["latitude"], f"row {row_number} latitude", lower=-90, upper=90
        )
        longitude = _finite_float(
            row["longitude"],
            f"row {row_number} longitude",
            lower=-180,
            upper=180,
        )
        service_text = str(row["service_duration_seconds"]).strip()
        service = 0.0 if not service_text else _finite_float(
            service_text, f"row {row_number} service_duration_seconds", lower=0
        )
        data_source = str(row["data_source"]).strip() or "undeclared"
        stops.append(
            DeliveryStop(
                stop_id=str(row["stop_id"]).strip(),
                stop_type=stop_type,
                delivery_priority=priority,
                name=str(row["name"]).strip(),
                latitude=latitude,
                longitude=longitude,
                address=str(row["address"]).strip(),
                service_duration_seconds=service,
                data_source=data_source,
            )
        )
    depots = [stop for stop in stops if stop.stop_type == "depot"]
    if len(depots) != 1:
        raise ValueError(
            f"Delivery stops must contain exactly one depot; found {len(depots)}"
        )
    deliveries = [stop for stop in stops if stop.stop_type == "delivery"]
    if not deliveries:
        raise ValueError("Delivery stops must contain at least one delivery stop")
    priorities = [stop.delivery_priority for stop in deliveries]
    if len(priorities) != len(set(priorities)):
        raise ValueError("Delivery-stop priorities must be unique")
    return tuple(stops)


def validate_item_stop_references(
    items: list[Item] | tuple[Item, ...], stops: tuple[DeliveryStop, ...]
) -> None:
    delivery_stops = {
        stop.stop_id: stop for stop in stops if stop.stop_type == "delivery"
    }
    unknown: list[str] = []
    mismatched: list[str] = []
    for item in items:
        attributes = delivery_attributes_for_item(item)
        if not attributes.declared_active:
            raise ValueError(
                f"Item {item.item_id} has no declared delivery metadata"
            )
        stop = delivery_stops.get(str(attributes.delivery_stop_id))
        if stop is None:
            unknown.append(f"{item.item_id}:{attributes.delivery_stop_id}")
        elif stop.delivery_priority != attributes.delivery_priority:
            mismatched.append(
                f"{item.item_id}:{attributes.delivery_stop_id} "
                f"item={attributes.delivery_priority} stop={stop.delivery_priority}"
            )
    if unknown:
        raise ValueError(
            "Items reference unknown delivery stops: " + ", ".join(unknown)
        )
    if mismatched:
        raise ValueError(
            "Item/stop delivery priorities disagree: " + ", ".join(mismatched)
        )


def ordered_route_stops(
    stops: tuple[DeliveryStop, ...], *, return_to_depot: bool
) -> tuple[DeliveryStop, ...]:
    depot = next(stop for stop in stops if stop.stop_type == "depot")
    deliveries = sorted(
        (stop for stop in stops if stop.stop_type == "delivery"),
        key=lambda stop: (int(stop.delivery_priority or 0), stop.stop_id),
    )
    return (depot, *deliveries, *((depot,) if return_to_depot else ()))


def write_optional_routing_artifacts(
    run_dir: Path,
    items: list[Item],
    config: dict[str, Any],
    metadata: dict[str, Any],
    bundle: ValidationBundle,
) -> None:
    options = routing_options(config)
    if not options["enabled"] or not bundle.result.valid:
        return
    root = find_project_root(__file__)
    source_path = Path(str(options["stops_file"]))
    if not source_path.is_absolute():
        source_path = root / source_path
    stops = load_delivery_stops(source_path)
    validate_item_stop_references(items, stops)
    provider_requested = str(options["provider"])
    warning: str | None = None
    try:
        if provider_requested == "google_routes":
            provider: RouteProvider = GoogleRoutesProvider(
                os.environ.get("GOOGLE_ROUTES_API_KEY", "")
            )
        else:
            provider = DeclaredOrderOfflineProvider(
                assumed_speed_kph=float(options["offline_speed_kph"])
            )
        route = provider.compute(
            stops,
            travel_mode=str(options["travel_mode"]),
            return_to_depot=bool(options["return_to_depot"]),
            timeout_seconds=float(options["timeout_seconds"]),
        )
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
        if provider_requested != "google_routes" or not options["fallback_to_offline"]:
            raise
        warning = f"Google Routes unavailable; deterministic offline fallback used: {exc}"
        route = DeclaredOrderOfflineProvider(
            assumed_speed_kph=float(options["offline_speed_kph"])
        ).compute(
            stops,
            travel_mode=str(options["travel_mode"]),
            return_to_depot=bool(options["return_to_depot"]),
            timeout_seconds=float(options["timeout_seconds"]),
        )
        route = replace(
            route, provider_requested=provider_requested, warning=warning
        )
    destination = run_dir / "routing"
    destination.mkdir(parents=True, exist_ok=False)
    _write_stops(destination / "delivery_stops.csv", stops)
    _write_json(destination / "route.json", route.payload())
    pd.DataFrame([leg.to_dict() for leg in route.legs]).to_csv(
        destination / "route_legs.csv", index=False, encoding="utf-8"
    )
    _write_json(destination / "request_snapshot.json", route.request_snapshot)
    _write_json(destination / "response_snapshot.json", route.response_snapshot)
    provider_metadata = {
        "schema_version": ROUTING_SCHEMA_VERSION,
        "provider_requested": provider_requested,
        "provider_used": route.provider_used,
        "fallback_used": route.provider_used != provider_requested,
        "warning": warning,
        "api_key_present": bool(os.environ.get("GOOGLE_ROUTES_API_KEY")),
        "api_key_persisted": False,
        "stops_file_sha256": sha256_file(destination / "delivery_stops.csv"),
        "route_file_sha256": sha256_file(destination / "route.json"),
        "route_legs_file_sha256": sha256_file(destination / "route_legs.csv"),
    }
    _write_json(destination / "provider_metadata.json", provider_metadata)
    metadata.update(
        {
            "routing_status": "VALID",
            "routing_provider_requested": provider_requested,
            "routing_provider_used": route.provider_used,
            "routing_fallback_used": route.provider_used != provider_requested,
            "routing_total_distance_meters": route.total_distance_meters,
            "routing_total_duration_seconds": route.total_duration_seconds,
            "routing_warning": warning,
        }
    )
    _register_routing_artifacts(run_dir, metadata)


def validate_optional_routing_artifacts(
    run_dir: Path,
    items: list[Item],
    config: dict[str, Any],
    *,
    packing_valid: bool,
) -> ValidationResult:
    options = routing_options(config)
    if not options["enabled"] or not packing_valid:
        return ValidationResult(True, [])
    issues: list[ValidationIssue] = []
    destination = run_dir / "routing"
    required = (
        "delivery_stops.csv",
        "route.json",
        "route_legs.csv",
        "provider_metadata.json",
        "request_snapshot.json",
        "response_snapshot.json",
    )
    missing = [name for name in required if not (destination / name).is_file()]
    if missing:
        return ValidationResult(
            False,
            [
                ValidationIssue(
                    "ROUTING_ARTIFACT_MISSING",
                    "Missing routing artifacts: " + ", ".join(missing),
                )
            ],
        )
    try:
        stops = load_delivery_stops(destination / "delivery_stops.csv")
        validate_item_stop_references(items, stops)
        route = json.loads(
            (destination / "route.json").read_text(encoding="utf-8")
        )
        legs = pd.read_csv(destination / "route_legs.csv")
        provider = json.loads(
            (destination / "provider_metadata.json").read_text(encoding="utf-8")
        )
        expected_order = [
            stop.stop_id
            for stop in ordered_route_stops(
                stops, return_to_depot=bool(options["return_to_depot"])
            )
        ]
        if route.get("ordered_stop_ids") != expected_order:
            raise ValueError("route stop order differs from declared delivery priority")
        expected_pairs = list(zip(expected_order, expected_order[1:]))
        actual_pairs = list(
            zip(
                legs["origin_stop_id"].astype(str),
                legs["destination_stop_id"].astype(str),
            )
        )
        if actual_pairs != expected_pairs:
            raise ValueError("route legs do not match the declared stop order")
        distance_total = float(legs["distance_meters"].sum())
        duration_total = float(legs["duration_seconds"].sum())
        if not math.isclose(
            distance_total,
            float(route["total_distance_meters"]),
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            raise ValueError("route distance total does not match route legs")
        if not math.isclose(
            duration_total,
            float(route["total_duration_seconds"]),
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            raise ValueError("route duration total does not match route legs")
        if provider.get("api_key_persisted") is not False:
            raise ValueError("provider metadata must prove API secrets were not persisted")
        for name, field in (
            ("delivery_stops.csv", "stops_file_sha256"),
            ("route.json", "route_file_sha256"),
            ("route_legs.csv", "route_legs_file_sha256"),
        ):
            if provider.get(field) != sha256_file(destination / name):
                raise ValueError(f"{name} checksum differs from provider metadata")
        combined = "\n".join(
            (destination / name).read_text(encoding="utf-8", errors="ignore")
            for name in required
        )
        secret = os.environ.get("GOOGLE_ROUTES_API_KEY")
        if secret and secret in combined:
            raise ValueError("Google Routes API key leaked into routing artifacts")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        issues.append(ValidationIssue("ROUTING_ARTIFACT_INVALID", str(exc)))
    return ValidationResult(not issues, issues)


def _register_routing_artifacts(
    run_dir: Path, metadata: dict[str, Any]
) -> None:
    manifest_path = run_dir / "manifest.json"
    metrics_path = run_dir / "metrics" / "metrics.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("artifacts", {}).setdefault("derived", []).extend(
        [
            "routing/delivery_stops.csv",
            "routing/route.json",
            "routing/route_legs.csv",
            "routing/provider_metadata.json",
            "routing/request_snapshot.json",
            "routing/response_snapshot.json",
        ]
    )
    _write_json(manifest_path, manifest)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in (
        "routing_status",
        "routing_provider_requested",
        "routing_provider_used",
        "routing_fallback_used",
        "routing_total_distance_meters",
        "routing_total_duration_seconds",
        "routing_warning",
    ):
        metrics[key] = metadata.get(key)
    _write_json(metrics_path, metrics)


def _write_stops(path: Path, stops: tuple[DeliveryStop, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STOP_COLUMNS)
        writer.writeheader()
        for stop in stops:
            row = stop.to_dict()
            row["delivery_priority"] = (
                "" if stop.delivery_priority is None else stop.delivery_priority
            )
            writer.writerow(row)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _google_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _google_request_payload(
    ordered: tuple[DeliveryStop, ...], travel_mode: str
) -> dict[str, Any]:
    def waypoint(stop: DeliveryStop) -> dict[str, Any]:
        return {
            "location": {
                "latLng": {
                    "latitude": stop.latitude,
                    "longitude": stop.longitude,
                }
            }
        }

    return {
        "origin": waypoint(ordered[0]),
        "destination": waypoint(ordered[-1]),
        "intermediates": [waypoint(stop) for stop in ordered[1:-1]],
        "travelMode": travel_mode,
        "computeAlternativeRoutes": False,
        "polylineQuality": "OVERVIEW",
    }


def _duration_seconds(value: Any) -> float:
    text = str(value)
    if not text.endswith("s"):
        raise ValueError(f"Unsupported Google duration value: {value!r}")
    return float(text[:-1])


def _haversine_meters(origin: DeliveryStop, destination: DeliveryStop) -> float:
    radius = 6_371_008.8
    lat1 = math.radians(origin.latitude)
    lat2 = math.radians(destination.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(destination.longitude - origin.longitude)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * radius * math.asin(math.sqrt(value))


def _finite_float(
    value: Any,
    field: str,
    *,
    lower: float,
    upper: float | None = None,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or result < lower or (
        upper is not None and result > upper
    ):
        limit = f"[{lower}, {upper}]" if upper is not None else f">= {lower}"
        raise ValueError(f"{field} must be within {limit}")
    return result


def _sanitize_mapping(value: Any, *, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_mapping(child, secrets=secrets)
            for key, child in value.items()
            if "key" not in key.lower() and "token" not in key.lower()
        }
    if isinstance(value, list):
        return [_sanitize_mapping(child, secrets=secrets) for child in value]
    if isinstance(value, str):
        result = value
        for secret in secrets:
            if secret:
                result = result.replace(secret, "[REDACTED]")
        return result
    return value


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    coordinates: list[tuple[float, float]] = []
    latitude = 0
    longitude = 0
    index = 0
    while index < len(encoded):
        latitude_delta, index = _decode_polyline_value(encoded, index)
        longitude_delta, index = _decode_polyline_value(encoded, index)
        latitude += latitude_delta
        longitude += longitude_delta
        coordinates.append((latitude / 1e5, longitude / 1e5))
    return coordinates


def _decode_polyline_value(encoded: str, index: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if index >= len(encoded):
            raise ValueError("Encoded polyline is truncated")
        value = ord(encoded[index]) - 63
        index += 1
        result |= (value & 0x1F) << shift
        shift += 5
        if value < 0x20:
            break
    decoded = ~(result >> 1) if result & 1 else result >> 1
    return decoded, index
