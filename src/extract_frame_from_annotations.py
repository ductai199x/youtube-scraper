import os

import decord
import matplotlib.animation as anim
import matplotlib.pyplot as plt
import pandas as pd
import torch
from torchvision.io import write_png
from tqdm.auto import tqdm

decord.bridge.set_bridge("torch")


from helper import get_all_files
from youtube_video_scrapper import dataset_root_dir

anno_df = pd.read_csv(f"{dataset_root_dir}/annotations.csv")


frame_extract_dir = f"{dataset_root_dir}/frame_extract"
if not os.path.exists(frame_extract_dir):
    os.makedirs(frame_extract_dir)


def extract_frames_from_anno(anno_line):
    (
        _,
        celeb_name,
        youtube_id,
        frame_range,
        res_w,
        res_h,
        is_watermarked,
        is_pristine,
        chop_begin,
        chop_end,
    ) = anno_line
    if int(res_w) != 1920 or int(res_h) != 1080:
        print(f"ERROR: {dataset_root_dir}/h264/{youtube_id}.mp4 does not have 1920x1080 resolution")
        return False
    if not os.path.exists(f"{dataset_root_dir}/h264/{youtube_id}.mp4"):
        print(f"ERROR: {dataset_root_dir}/h264/{youtube_id}.mp4 does not exists")
        return False

    celeb_dir = f"{frame_extract_dir}/{'_'.join(celeb_name.split())}"
    pristine_dir = f"{celeb_dir}/pristine"
    watermark_dir = f"{celeb_dir}/watermark"
    other_dir = f"{celeb_dir}/other"

    if is_pristine == 1:
        save_to_dir = pristine_dir
    else:
        if is_watermarked == 1:
            save_to_dir = watermark_dir
        else:
            save_to_dir = other_dir
    save_to_dir = f"{save_to_dir}/{youtube_id}"
    if not os.path.exists(save_to_dir):
        os.makedirs(save_to_dir)

    frame_begin, frame_end = map(int, frame_range.split("-"))
    if chop_begin == -1:
        chop_begin = 0
    if chop_end == -1:
        chop_end = frame_end - frame_begin
    chop_frame_begin, chop_frame_end = frame_begin + chop_begin, frame_begin + chop_end
    
    try:
        vr = decord.VideoReader(f"{dataset_root_dir}/h264/{youtube_id}.mp4")
        if chop_frame_end > len(vr):
            print(f"WARNING: {dataset_root_dir}/h264/{youtube_id}.mp4 has chop_frame_end={chop_frame_end} > max={len(vr)}")
            chop_frame_end = len(vr)
        fr_batch = list(range(chop_frame_begin, chop_frame_end))
        batch = vr.get_batch(fr_batch).permute(0, 3, 1, 2)
        del vr

        for idx, im in zip(fr_batch, batch):
            if not os.path.exists(f"{save_to_dir}/{idx}.png"):
                write_png(im, f"{save_to_dir}/{idx}.png", compression_level=0)

        return True
    except Exception as e:
        print(f"ERROR: {dataset_root_dir}/h264/{youtube_id}.mp4 fail with {e}")
        return False


with tqdm(anno_df["celeb_name"].unique()) as pbar:
    for celeb in pbar:
        pbar.set_description(f"Celeb={celeb}")
        for anno_line in tqdm(anno_df.query(f"`celeb_name` == '{celeb}'").to_numpy(), desc=f"Celeb={celeb}"):
            extract_frames_from_anno(anno_line)
