"""Create a small, dedicated COCO validation dataset for App acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import uuid
import zipfile
from collections import defaultdict
from importlib import import_module
from pathlib import Path

import fiftyone as fo
import numpy as np
from fiftyone.utils.coco import COCOObject

# Fixed selection: CC BY images chosen with seed 51, plus a regression image.
ACCEPTANCE_IDS = (138979, 130586, 260106, 448076, 81988, 119445, 261888, 231508, 570756, 378116, 350148, 48564)
RECORDING_IDS = (130586, 261888, 378116)
IMAGE_BASE = "https://s3.us-east-1.amazonaws.com/images.cocodataset.org/val2017/"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True, help="Official annotations_trainval2017.zip")
    parser.add_argument("--data-dir", type=Path, required=True, help="Dedicated local image/manifest directory")
    parser.add_argument("--name", default=None, help="New dataset name; existing datasets are never overwritten")
    parser.add_argument("--recording-only", action="store_true", help="Use the three CC BY studio photographs")
    args = parser.parse_args()
    try:
        import_module("pycocotools.mask")
    except ImportError as error:
        raise SystemExit("Install the optional pycocotools dependency to import actual instance masks.") from error

    name = args.name or f"albumentationsx-coco-{uuid.uuid4().hex[:8]}"
    if fo.dataset_exists(name):
        raise SystemExit(f"Dataset already exists: {name}. Choose a new name.")
    with zipfile.ZipFile(args.annotations) as archive:
        instances = json.loads(archive.read("annotations/instances_val2017.json"))
        poses = json.loads(archive.read("annotations/person_keypoints_val2017.json"))

    ids = RECORDING_IDS if args.recording_only else ACCEPTANCE_IDS
    images = {image["id"]: image for image in instances["images"]}
    classes = {category["id"]: category["name"] for category in instances["categories"]}
    licenses = {license["id"]: license for license in instances["licenses"]}
    annotations: dict[int, list] = defaultdict(list)
    keypoint_annotations: dict[int, list] = defaultdict(list)
    for annotation in instances["annotations"]:
        if annotation["image_id"] in ids:
            annotations[annotation["image_id"]].append(annotation)
    for annotation in poses["annotations"]:
        if annotation["image_id"] in ids and annotation["num_keypoints"] > 0:
            keypoint_annotations[annotation["image_id"]].append(annotation)

    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    source_records = []
    mask_count = pose_count = missing_joint_count = 0
    for image_id in ids:
        image = images[image_id]
        if args.recording_only and image["license"] != 4:
            raise SystemExit(f"Recording image {image_id} is not marked CC BY in the official metadata.")
        filename = f"{image_id:012d}.jpg"
        path = data_dir / filename
        if not path.exists():
            urllib.request.urlretrieve(IMAGE_BASE + filename, path)  # noqa: S310
        size = (image["width"], image["height"])
        detections = [
            COCOObject(**annotation).to_detection(size, classes_map=classes, load_segmentation=True, include_id=True)
            for annotation in annotations[image_id]
        ]
        keypoints = [
            COCOObject(**annotation).to_keypoints(size, classes_map=classes, include_id=True)
            for annotation in keypoint_annotations[image_id]
        ]
        detections = [d for d in detections if d is not None]
        keypoints = [k for k in keypoints if k is not None]
        mask_count += sum(d.mask is not None and bool(np.asarray(d.mask).any()) for d in detections)
        pose_count += len(keypoints)
        missing_joint_count += sum(int(np.isnan(np.asarray(k.points)[:, 0]).sum()) for k in keypoints)
        sample = fo.Sample(
            filepath=str(path),
            coco_id=image_id,
            tags=["coco-acceptance"],
            metadata=fo.ImageMetadata(width=size[0], height=size[1]),
            detections=fo.Detections(detections=detections),
            keypoints=fo.Keypoints(keypoints=keypoints),
        )
        samples.append(sample)
        source_records.append(
            {
                "coco_id": image_id,
                "filepath": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "license": licenses[image["license"]],
                "original_url": image["flickr_url"],
                "detections": sample.detections.to_json(),
                "keypoints": sample.keypoints.to_json(),
            }
        )
    if not (mask_count and pose_count and missing_joint_count):
        raise SystemExit("Acceptance data must contain nonempty masks, person poses, and missing joints.")

    dataset = fo.Dataset(name)
    dataset.add_samples(samples)
    category = poses["categories"][0]
    dataset.default_skeleton = fo.KeypointSkeleton(
        labels=category["keypoints"], edges=[[index - 1 for index in edge] for edge in category["skeleton"]]
    )
    dataset.persistent = True
    summary = {
        "dataset": name,
        "image_ids": ids,
        "nonempty_masks": mask_count,
        "person_poses": pose_count,
        "missing_joints": missing_joint_count,
    }
    # Each invocation gets its own baseline; never replace another dataset's audit.
    manifest = data_dir / f"acceptance-{uuid.uuid4().hex}.json"
    manifest.write_text(json.dumps({**summary, "sources": source_records}, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "baseline": str(manifest)}, indent=2))


if __name__ == "__main__":
    main()
