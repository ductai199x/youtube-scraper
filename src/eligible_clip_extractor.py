import math
import re
import os
import pickle
from typing import *

import decord
import torch
import torchvision
from tqdm.auto import tqdm

from face_mesh_detector import FaceMeshDetector
from helper import get_all_files

decord.bridge.set_bridge("torch")

dataset_root_dir = "/media/nas2/Tai/4-deepfake-data"
download_dir = f"{dataset_root_dir}/downloads"
extract_dir = f"{dataset_root_dir}/output"
scaler = 0.3
resize_fn = torchvision.transforms.Resize((int(1080 * scaler), int(1920 * scaler)))
max_frames_per_batch = 80
max_frames_per_clip = 700
is_gpu = False
gpu_idx = 0


def get_num_faces_in_videos(video_path: str) -> List[int]:
    """This function extract the number of faces for every second of the video
    specified in `video_path`.

    Args:
        video_path (str): the path to the video

    Returns:
        List[int]: each number in the list correspond to the number of faces in that frame
        (one frame correspond to a second)
    """
    vr = decord.VideoReader(video_path, ctx=decord.gpu(gpu_idx) if is_gpu else decord.cpu(0))
    avg_fps = math.ceil(vr.get_avg_fps())
    max_nframes = len(vr)
    print(f"{video_path}: Total number of frames = {max_nframes}, avg_fps = {avg_fps}")

    batches = list(torch.arange(0, max_nframes - avg_fps, avg_fps).split(max_frames_per_batch))

    face_markers = []
    for batch in batches:
        frame_batch = vr.get_batch(batch).permute(0, 3, 1, 2)
        resize_batch = resize_fn(frame_batch)
        resize_batch = resize_batch.permute(0, 2, 3, 1).cpu().numpy()
        for frame in resize_batch:
            FACE_DETECTOR = FaceMeshDetector(maxFaces=2)
            _, faces = FACE_DETECTOR.findFaceMesh(frame, draw=True)
            face_markers.append(len(faces))
    return face_markers, avg_fps


def choose_eligible_seqs(face_markers: List[int], fps: int, num_faces=1, min_sec_per_seq=10) -> List:
    """Only choose seqs with `num_faces` faces that's continuous for `min_sec_per_seq`.

    Args:
        face_markers (List[int]): each number in the list correspond to the number of faces in that frame
        (one frame correspond to a second)
        fps (int): the fps of the video
        num_faces (int, optional): number of faces in a frame. Defaults to 1.
        min_sec_per_seq (int, optional): minimum number of seconds per sequences. Defaults to 10.

    Returns:
        List: a list of tuple, each tuple consist of 2 ints - (start frame #, end frame #)
    """
    start_idx = -1
    end_idx = 0
    subseqlen = 0
    seqnum = -1

    eligible_seqs = []
    for i, m in enumerate(face_markers):
        if seqnum == -1:
            start_idx = i
            seqnum = m
        if m != seqnum:
            end_idx = i
            subseqlen = end_idx - start_idx
            if seqnum == num_faces and subseqlen >= min_sec_per_seq:
                start_frame = i = start_idx * fps
                end_frame = end_idx * fps
                total_frame = end_frame - start_frame
                num_frames_per_clip = max_frames_per_clip
                while i < end_frame:
                    eligible_seqs.append((i, i + num_frames_per_clip))
                    i += num_frames_per_clip
            start_idx = i
            seqnum = m
    return eligible_seqs


def extract_seqs(video_path: str, start_idx: int, end_idx: int, fps: int, prefix=""):
    """Take video path, start frame #, and end frame #, fps and prefix and produce

    Args:
        video_path (str): the path to the video
        start_idx (int): start frame #
        end_idx (int): end frame #
        fps (int): average fps
        prefix (str, optional): output file prefix. Defaults to "".
    """
    vr = decord.VideoReader(video_path, ctx=decord.gpu(gpu_idx) if is_gpu else decord.cpu(0))
    if start_idx >= len(vr): return
    batches = vr.get_batch(list(torch.arange(start_idx, min(end_idx, len(vr))))).cpu()
    torchvision.io.write_video(f"{extract_dir}/{prefix}_{start_idx}_{end_idx}.mp4", batches, fps)


def main():
    # Create the output folder
    if not os.path.exists(extract_dir):
        os.makedirs(extract_dir)

    # video_paths = get_all_files(download_dir, suffix="mp4")
    with open(f"{dataset_root_dir}/metadata.pkl", "rb") as f:
        metadata = pickle.load(f)

    for url in tqdm(metadata):
        video_path = metadata[url]["path"]
        celeb_name = metadata[url]["search_string"]
        video_id = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)[0]
        if not os.path.exists(video_path):
            continue
        dir, fname = os.path.split(video_path)
        basename, ext = os.path.splitext(fname)
        face_markers, avg_fps = get_num_faces_in_videos(video_path)
        eligible_seqs = choose_eligible_seqs(face_markers, avg_fps, num_faces=1, min_sec_per_seq=10)
        for start_idx, end_idx in tqdm(eligible_seqs):
            extract_seqs(video_path, start_idx, end_idx, avg_fps, prefix=f"{celeb_name}_{video_id}")


if __name__ == "__main__":
    main()

# empty_mask = np.zeros((int(1080 * scaler), int(1920 * scaler), 3)).astype(np.uint8)
# if len(faces) == 1:
#     face = np.array(faces[0], dtype=np.int32)
#     sel = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
#         152, 148, 176, 140, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
#     face = face[sel]
#     hull = ConvexHull(face)
#     face_contour = face[hull.vertices]
#     mask = empty_mask.copy().astype(np.float64)
#     # mask = np.zeros(frame.shape)
#     mask = cv2.polylines(mask, [face_contour], True, (1, 1, 1), thickness=2, lineType=cv2.LINE_8)
#     mask = cv2.fillPoly(mask, [face_contour], (1, 1, 1), lineType=cv2.LINE_AA)
#     plt.imsave(f"{output_frames_folder}/mask_{len(faces_marker) - 1}.png", mask)
#     plt.imsave(f"{output_frames_folder}/frame_{len(faces_marker) - 1}.png", frame)
