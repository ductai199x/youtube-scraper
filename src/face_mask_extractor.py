import math
import os
import shutil

import cv2
import decord
import matplotlib.pyplot as plt
import numpy as np
import torch
import torchvision
from scipy.spatial import ConvexHull
from tqdm.auto import tqdm

from face_mesh_detector import FaceMeshDetector

decord.bridge.set_bridge("torch")

output_frames_folder = "./output"
if not os.path.exists(output_frames_folder):
    os.makedirs(output_frames_folder)
else:
    if len(os.listdir(output_frames_folder)):
        shutil.rmtree(output_frames_folder)
        os.makedirs(output_frames_folder)

video_path = "test.mp4"
vr = decord.VideoReader(video_path, decord.gpu(1))
avg_fps = math.ceil(vr.get_avg_fps())
max_nframes = len(vr)
max_frames_per_batch = 80
batches = list(torch.arange(0, max_nframes, avg_fps).split(max_frames_per_batch))

scaler = 0.25
resize = torchvision.transforms.Resize((int(1080 * scaler), int(1920 * scaler)))

FACE_DETECTOR = FaceMeshDetector(maxFaces=2)

faces_marker = []

empty_mask = np.zeros((int(1080 * scaler), int(1920 * scaler), 3)).astype(np.uint8)

for batch in tqdm(batches):
    frame_batch = vr.get_batch(batch)
    frame_batch = frame_batch.permute(0, 3, 1, 2)
    resize_batch = resize(frame_batch)
    resize_batch = resize_batch.permute(0, 2, 3, 1).cpu().numpy()
    for frame in resize_batch:
        _, _ = FACE_DETECTOR.findFaceMesh(empty_mask, draw=False)
        _, _ = FACE_DETECTOR.findFaceMesh(empty_mask, draw=False)
        _, faces = FACE_DETECTOR.findFaceMesh(frame, draw=True)
        faces_marker.append(len(faces))
        if len(faces) == 1:
            face = np.array(faces[0], dtype=np.int32)
            # sel = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
            #     152, 148, 176, 140, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
            # face = face[sel]
            hull = ConvexHull(face)
            face_contour = face[hull.vertices]
            mask = empty_mask.copy().astype(np.float64)
            # mask = np.zeros(frame.shape)
            mask = cv2.polylines(mask, [face_contour], True, (1, 1, 1), thickness=2, lineType=cv2.LINE_8)
            mask = cv2.fillPoly(mask, [face_contour], (1, 1, 1), lineType=cv2.LINE_AA)
            plt.imsave(f"{output_frames_folder}/mask_{len(faces_marker) - 1}.png", mask)
            plt.imsave(f"{output_frames_folder}/frame_{len(faces_marker) - 1}.png", frame)

start_idx = -1
end_idx = 0
subseqlen = 0
seqnum = -1

eligible_seqs = []

for i, m in enumerate(faces_marker):
    if seqnum == -1:
        start_idx = i
        seqnum = m
    if m != seqnum:
        end_idx = i
        subseqlen = end_idx - start_idx
        if seqnum == 1 and subseqlen >= 10:
            eligible_seqs.append((start_idx, end_idx))
        start_idx = i
        seqnum = m

print(eligible_seqs)
