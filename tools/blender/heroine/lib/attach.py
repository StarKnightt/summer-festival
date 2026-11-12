"""Attachment points (rest pose, Blender lifted frame) and their bone-local offsets.

hand_R palm centre: where a held prop (the candy-apple stick) sits, on the palm 13 mm off its
surface; grip axis = the direction a stick held in the fist runs (thumb side -> little finger).
head mask: a festival mask worn tilted on the right side of her head, its back on the hair.
"""
import numpy as np

from . import rig
from . import shape as S
from .common import norm


def points():
    hp = rig.hand_points()
    d, w, n = hp["d"], hp["w"], hp["n"]
    palm_L = hp["wrist"] + d * 0.048 + n * 0.013
    grip_L = hp["wrist"] + d * 0.060 + n * 0.022
    lift = np.array([0, 0, S.SOLE])
    m = np.array([-1.0, 1, 1])
    out = {
        "hand_R.palmCentre": (palm_L * m + lift, "hand_R"),
        "hand_R.gripCentre": (grip_L * m + lift, "hand_R"),
        "head.maskCentre": (np.array([-0.097, -0.004, 1.437]) + lift, "head"),
    }
    dirs = {
        "hand_R.palmNormal": (n * m, "hand_R"),
        "hand_R.gripAxis": (-w * m, "hand_R"),          # thumb -> little finger, the stick's direction
        "head.maskForward": (norm(np.array([-1.0, -0.30, 0.25])), "head"),   # the mask's face points out right, a bit forward/up
        "head.maskUp": (norm(np.array([0.15, 0.10, 1.0])), "head"),
    }
    return out, dirs
