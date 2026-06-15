from __future__ import annotations

from pathlib import Path

import numpy as np

from benchmarks.modal.promptable_segmentation_shared import (
    bbox_iou,
    build_promptable_scene_suite,
    mask_iou,
    promptability_score,
)


def test_promptable_scene_suite_builds_frames(tmp_path):
    scenes = build_promptable_scene_suite(tmp_path / "suite", scene_count=2, frame_count=3, size=256)

    assert len(scenes) == 2
    assert all(len(scene.frames) == 3 for scene in scenes)
    assert all(Path(frame.image_path).exists() for scene in scenes for frame in scene.frames)
    assert all(scene.prompt for scene in scenes)
    assert all(scene.reference_frame.target.label == scene.prompt for scene in scenes)


def test_promptable_metrics_cover_masks_and_boxes():
    gt = np.zeros((20, 20), dtype=bool)
    gt[4:14, 4:14] = True
    pred = np.zeros((20, 20), dtype=bool)
    pred[5:13, 5:13] = True

    assert 0.5 < mask_iou(pred, gt) < 1.0
    assert 0.5 < bbox_iou((5, 5, 13, 13), (4, 4, 14, 14)) < 1.0

    metrics = promptability_score(pred, gt, (4, 4, 14, 14))
    assert metrics["mask_iou"] > 0.5
    assert metrics["pixel_acc"] > 0.5
    assert metrics["bbox_iou"] > 0.45
