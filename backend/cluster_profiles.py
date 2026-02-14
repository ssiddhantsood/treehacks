import csv
import json
import os
import time
import urllib.request
import urllib.error
from typing import List, Dict, Any, Tuple

import numpy as np


def _row_to_text(row: Dict[str, str]) -> str:
    return (
        f"age: {row.get('age', '')}; "
        f"gender: {row.get('gender', '')}; "
        f"demographic: {row.get('demographic_info', '')}; "
        f"previous_search_history: {row.get('previous_search_history', '')}"
    )


def _load_rows(csv_path: str) -> List[Dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def _parse_embeddings_response(data: Dict[str, Any]) -> List[List[float]]:
    text_embedding = data.get("text_embedding")
    if isinstance(text_embedding, list):
        if text_embedding and isinstance(text_embedding[0], dict) and "embedding" in text_embedding[0]:
            return [item["embedding"] for item in text_embedding]
        if text_embedding and isinstance(text_embedding[0], list):
            return text_embedding
    if "embedding" in data and isinstance(data["embedding"], list):
        return data["embedding"]
    if "embeddings" in data and isinstance(data["embeddings"], list):
        return data["embeddings"]
    raise ValueError("Unexpected embeddings response shape")


def _post_json(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: int) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def _embed_texts(
    texts: List[str],
    endpoint: str,
    api_key: str,
    inference_id: str,
    input_type: str = "CLUSTERING",
    batch_size: int = 16,
    timeout: int = 30,
    retry_without_input_type: bool = True,
) -> List[List[float]]:
    if not endpoint or not api_key or not inference_id:
        raise ValueError("endpoint, api_key, and inference_id are required")

    if endpoint.endswith("/"):
        endpoint = endpoint[:-1]
    url = f"{endpoint}/_inference/text_embedding/{inference_id}"

    headers = {"Authorization": f"ApiKey {api_key}"}

    all_embeddings: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        body: Dict[str, Any] = {"input": batch}
        if input_type:
            body["input_type"] = input_type

        try:
            data = _post_json(url, body, headers, timeout)
        except urllib.error.HTTPError as e:
            if retry_without_input_type and input_type:
                # Some services don't accept input_type; retry once without it.
                fallback = {"input": batch}
                data = _post_json(url, fallback, headers, timeout)
            else:
                raise e

        batch_embeddings = _parse_embeddings_response(data)
        if len(batch_embeddings) != len(batch):
            raise ValueError("Embedding count does not match input batch size")
        all_embeddings.extend(batch_embeddings)
        time.sleep(0.05)  # small pause to avoid rate spikes

    return all_embeddings


def _kmeans(
    vectors: np.ndarray, n_clusters: int, max_iter: int = 100, seed: int = 42
) -> Tuple[np.ndarray, np.ndarray]:
    if n_clusters <= 0:
        raise ValueError("n_clusters must be > 0")
    if n_clusters > len(vectors):
        raise ValueError("n_clusters cannot exceed number of samples")

    rng = np.random.default_rng(seed)
    indices = rng.choice(len(vectors), size=n_clusters, replace=False)
    centroids = vectors[indices]

    for _ in range(max_iter):
        distances = np.linalg.norm(vectors[:, None, :] - centroids[None, :, :], axis=2)
        labels = distances.argmin(axis=1)

        new_centroids = np.zeros_like(centroids)
        for k in range(n_clusters):
            members = vectors[labels == k]
            if len(members) == 0:
                # Reinitialize empty cluster to a random point
                new_centroids[k] = vectors[rng.integers(0, len(vectors))]
            else:
                new_centroids[k] = members.mean(axis=0)

        if np.allclose(centroids, new_centroids, atol=1e-6):
            break
        centroids = new_centroids

    return labels, centroids


def cluster(
    n_clusters: int,
    csv_path: str = "mock_profiles.csv",
    inference_id: str | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
    input_type: str = "CLUSTERING",
    batch_size: int = 16,
) -> List[Dict[str, Any]]:
    rows = _load_rows(csv_path)
    texts = [_row_to_text(r) for r in rows]

    endpoint = endpoint or os.getenv("ELASTICSEARCH_ENDPOINT")
    api_key = api_key or os.getenv("ELASTIC_API_KEY")
    inference_id = inference_id or os.getenv("ELASTIC_INFERENCE_ID")

    embeddings = _embed_texts(
        texts,
        endpoint=endpoint,
        api_key=api_key,
        inference_id=inference_id,
        input_type=input_type,
        batch_size=batch_size,
    )

    vectors = np.array(embeddings, dtype=np.float32)
    labels, _ = _kmeans(vectors, n_clusters)

    clustered = []
    for row, label in zip(rows, labels):
        out = dict(row)
        out["cluster"] = int(label)
        clustered.append(out)

    return clustered
