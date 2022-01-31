import torch
import torchvision
import math
import decord
import matplotlib.pyplot as plt
import numpy as np
from multiprocessing import Pool
from tqdm.auto import tqdm
from facemeshdetector import FaceMeshDetector

decord.bridge.set_bridge("torch")

video_path = "/home/bigboy/1-workdir/1-youtube-scraper/test_ed.mp4"
vr = decord.VideoReader(video_path, decord.gpu(0))
avg_fps = math.ceil(vr.get_avg_fps())
max_nframes = len(vr)
max_frames_per_batch = 100
batches = list(torch.arange(0, max_nframes, avg_fps).split(max_frames_per_batch))

scaler = 0.25
resize = torchvision.transforms.Resize((int(1080 * scaler), int(1920 * scaler)))


def get_faces(frame):
    FACE_DETECTOR = FaceMeshDetector(maxFaces=2)
    _, faces = FACE_DETECTOR.findFaceMesh(frame)
    # print(frame.shape)
    return 1
    # pass


with Pool(10) as p:
    for batch in tqdm(batches):
        frame_batch = vr.get_batch(batch)
        frame_batch = frame_batch.permute(0, 3, 1, 2)
        resize_batch = resize(frame_batch)
        resize_batch = resize_batch.permute(0, 2, 3, 1).cpu().numpy()
        result = p.map(get_faces, resize_batch)
        # break
        # for frame in resize_batch:
        #     _, faces = FACE_DETECTOR.findFaceMesh(frame)
        # fig, ax = plt.subplots(1)
        # fig.subplots_adjust(left=0, right=1)
        # ax.imshow(frame, aspect="auto", extent=(0, 1, 1, 0))
        # ax.axis("tight")
        # ax.axis("off")
