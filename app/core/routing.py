import heapq

# 7 Nodes with GeoJSON coordinates [lng, lat]
NODES = {
    "N1": {"name": "Incident Zone N1", "coords": [77.5850, 12.9650], "elevation": 910, "dist_river": 3.2, "drainage": 0.7, "rainfall": 25.0},
    "N2": {"name": "Junction North N2", "coords": [77.5950, 12.9750], "elevation": 920, "dist_river": 2.1, "drainage": 0.6, "rainfall": 30.0},
    "N3": {"name": "Junction West N3", "coords": [77.5750, 12.9600], "elevation": 895, "dist_river": 0.8, "drainage": 0.4, "rainfall": 45.0},
    "N4": {"name": "Junction Central N4", "coords": [77.6000, 12.9650], "elevation": 915, "dist_river": 2.5, "drainage": 0.8, "rainfall": 20.0},
    "N5": {"name": "Hospital A N5", "coords": [77.5900, 12.9800], "elevation": 930, "dist_river": 4.0, "drainage": 0.9, "rainfall": 15.0},
    "N6": {"name": "Hospital B N6", "coords": [77.6150, 12.9700], "elevation": 925, "dist_river": 3.5, "drainage": 0.85, "rainfall": 18.0},
    "N7": {"name": "Hospital C N7", "coords": [77.5700, 12.9500], "elevation": 890, "dist_river": 1.2, "drainage": 0.5, "rainfall": 40.0}
}

DEFAULT_ROADS = [
    {"_id": "R1", "src": "N1", "dst": "N2", "travel_time": 5.0, "risk": 0.2, "name": "North Avenue", "blocked": 0},
    {"_id": "R2", "src": "N1", "dst": "N3", "travel_time": 7.0, "risk": 0.6, "name": "West Highway", "blocked": 0},
    {"_id": "R3", "src": "N2", "dst": "N5", "travel_time": 6.0, "risk": 0.3, "name": "St. Jude Link", "blocked": 0},
    {"_id": "R4", "src": "N2", "dst": "N4", "travel_time": 4.0, "risk": 0.1, "name": "Central Bypass", "blocked": 0},
    {"_id": "R5", "src": "N3", "dst": "N4", "travel_time": 5.0, "risk": 0.4, "name": "West-Central Connector", "blocked": 0},
    {"_id": "R6", "src": "N4", "dst": "N6", "travel_time": 8.0, "risk": 0.2, "name": "Metro Expressway", "blocked": 0},
    {"_id": "R7", "src": "N3", "dst": "N7", "travel_time": 6.0, "risk": 0.3, "name": "Community Link", "blocked": 0},
    {"_id": "R8", "src": "N4", "dst": "N7", "travel_time": 7.0, "risk": 0.2, "name": "South Connector", "blocked": 0},
    {"_id": "R9", "src": "N2", "dst": "N6", "travel_time": 10.0, "risk": 0.5, "name": "Ring Road East", "blocked": 0}
]

def find_nearest_node(lat: float, lng: float) -> str:
    if lat is None or lng is None:
        return "N1"
    # Check if within demo bounding box approx: lat 12.8-13.1, lng 77.4-77.7
    if not (12.8 <= lat <= 13.1 and 77.4 <= lng <= 77.7):
        return "N1"

    best_node = "N1"
    min_dist = float("inf")
    for n_id, n_data in NODES.items():
        n_lng, n_lat = n_data["coords"]
        d = (lat - n_lat)**2 + (lng - n_lng)**2
        if d < min_dist:
            min_dist = d
            best_node = n_id
    return best_node

def find_shortest_path(start_node: str, end_node: str, roads_list: list[dict], risk_multiplier: float = 1.0) -> dict:
    if start_node == end_node:
        coords = NODES[start_node]["coords"] if start_node in NODES else [77.5850, 12.9650]
        return {
            "nodes": [start_node],
            "coords": [coords],
            "travel_time": 0.0,
            "avg_risk": 0.0,
            "weighted_cost": 0.0,
            "road_ids": []
        }

    # Build adjacency list
    graph = {}
    for r in roads_list:
        if r.get("blocked", 0) == 1:
            continue
        src = r["src"]
        dst = r["dst"]
        t_time = float(r["travel_time"])
        r_risk = float(r.get("risk", 0.1))
        # Edge weight = travel_time * (1 + 0.8 * edge_risk * risk_multiplier)
        weight = t_time * (1.0 + 0.8 * r_risk * risk_multiplier)

        road_info = {
            "id": r["_id"],
            "name": r.get("name", r["_id"]),
            "travel_time": t_time,
            "risk": r_risk,
            "weight": weight
        }

        graph.setdefault(src, []).append((dst, road_info))
        graph.setdefault(dst, []).append((src, road_info))

    # Priority queue: (cost, current_node, path_nodes, path_roads, total_time, total_risk_weighted)
    pq = [(0.0, start_node, [start_node], [], 0.0, 0.0)]
    visited = set()

    while pq:
        cost, curr, path, roads, t_time, r_weighted = heapq.heappop(pq)

        if curr in visited:
            continue
        visited.add(curr)

        if curr == end_node:
            avg_risk = (r_weighted / t_time) if t_time > 0 else 0.0
            coords = [NODES[n]["coords"] for n in path if n in NODES]
            return {
                "nodes": path,
                "coords": coords,
                "travel_time": round(t_time, 2),
                "avg_risk": round(avg_risk, 3),
                "weighted_cost": round(cost, 2),
                "road_ids": roads
            }

        for neighbor, edge in graph.get(curr, []):
            if neighbor not in visited:
                next_cost = cost + edge["weight"]
                next_time = t_time + edge["travel_time"]
                next_r_weighted = r_weighted + (edge["risk"] * edge["travel_time"])
                heapq.heappush(pq, (
                    next_cost,
                    neighbor,
                    path + [neighbor],
                    roads + [edge["id"]],
                    next_time,
                    next_r_weighted
                ))

    # If unreachable (all roads blocked)
    start_coords = NODES.get(start_node, {}).get("coords", [77.5850, 12.9650])
    end_coords = NODES.get(end_node, {}).get("coords", [77.5900, 12.9800])
    return {
        "nodes": [start_node, end_node],
        "coords": [start_coords, end_coords],
        "travel_time": 999.0,
        "avg_risk": 1.0,
        "weighted_cost": 9999.0,
        "road_ids": []
    }
