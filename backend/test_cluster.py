import hashlib
import os
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

import numpy as np

import cluster_profiles


def _hash_embed(texts: List[str], dim: int = 64) -> np.ndarray:
    vectors = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        for token in text.lower().split():
            token = token.strip(".,;:()[]{}!?")
            if not token:
                continue
            h = hashlib.md5(token.encode("utf-8")).hexdigest()
            idx = int(h, 16) % dim
            vectors[i, idx] += 1.0

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _split_tags(value: str, sep: str) -> List[str]:
    return [part.strip().lower() for part in value.split(sep) if part.strip()]


def _describe_clusters(
    rows: List[Dict[str, str]], labels: np.ndarray
) -> Tuple[Dict[int, List[Dict[str, str]]], Dict[int, Dict[str, List[str]]]]:
    clusters: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    for row, label in zip(rows, labels):
        clusters[int(label)].append(row)

    descriptions: Dict[int, Dict[str, List[str]]] = {}
    for label, members in clusters.items():
        demo_counter = Counter()
        search_counter = Counter()
        for row in members:
            demo_counter.update(_split_tags(row.get("demographic_info", ""), ","))
            search_counter.update(_split_tags(row.get("previous_search_history", ""), ";"))

        descriptions[label] = {
            "top_demographics": [t for t, _ in demo_counter.most_common(6)],
            "top_searches": [t for t, _ in search_counter.most_common(6)],
        }

    return clusters, descriptions


def run(n_clusters: int = 4) -> None:
    csv_path = os.path.join(os.path.dirname(__file__), "mock_profiles.csv")
    rows = cluster_profiles._load_rows(csv_path)
    texts = [cluster_profiles._row_to_text(r) for r in rows]

    vectors = _hash_embed(texts, dim=96)
    labels, _ = cluster_profiles._kmeans(vectors, n_clusters=n_clusters, seed=7)

    clusters, descriptions = _describe_clusters(rows, labels)

    print(f"Clustered {len(rows)} profiles into {n_clusters} groups\n")

    for label in sorted(clusters.keys()):
        members = clusters[label]
        desc = descriptions[label]
        print(f"Cluster {label} ({len(members)} profiles)")
        print("Top demographics:", ", ".join(desc["top_demographics"]))
        print("Top searches:", ", ".join(desc["top_searches"]))
        print("Examples:")
        for row in members[:3]:
            print(
                f"- age {row.get('age')}, {row.get('gender')}: {row.get('demographic_info')}"
            )
        print("")


if __name__ == "__main__":
    run()
