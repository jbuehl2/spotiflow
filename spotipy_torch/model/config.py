import abc
import argparse
import logging
import json
import yaml
import sys

from numbers import Number
from pathlib import Path
from typing import Literal, Optional, Tuple, Union

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
log = logging.getLogger(__name__)

class SpotipyConfig(argparse.Namespace, abc.ABC):
    def __init__(self):
        self.is_valid()

    @classmethod
    def from_config_file(cls, f: Union[str, Path]):
        if isinstance(f, str):
            f = Path(f)
        assert f.is_file(), f"Config file {f} does not exist."
        if f.suffix == ".json":
            with open(f, "r") as fp:
                loaded_dct = json.load(fp)
        elif f.suffix in {".yml", ".yaml"}:
            with open(f, "r") as fp:
                loaded_dct = yaml.safe_load(fp)
        else:
            raise ValueError(f"Config file {f} must be either a JSON or YAML file.")
        if "downsample_factors" in loaded_dct.keys():
            loaded_dct["downsample_factors"] = tuple(tuple(ft) for ft in loaded_dct["downsample_factors"])
        if "kernel_sizes" in loaded_dct.keys():
            loaded_dct["kernel_sizes"] = tuple(tuple(kt) for kt in loaded_dct["kernel_sizes"])    
        config = cls(**loaded_dct)
        return config
    
    def save(self, f: Union[str, Path]) -> None:
        if isinstance(f, str):
            f = Path(f)
        cfg_dict = vars(self)

        for k, v in cfg_dict.items():
            if isinstance(v, Path):
                cfg_dict[k] = str(v)

        if f.suffix == ".json":
            with open(f, "w") as fp:
                json.dump(cfg_dict, fp, indent=4)
        elif f.suffix in {".yml", ".yaml"}:
            with open(f, "w") as fp:
                yaml.safe_dump(cfg_dict, fp, indent=4)
        else:
            raise ValueError(f"Config file {f} must be either a JSON or YAML file.")
        return
    
    def __str__(self):
        pre = f"{self.__class__.__name__}(\n"
        post = "\n)"
        return pre+"\n".join([f"\t{att}={val}" for att, val in sorted(vars(self).items(), key=lambda x: x[0])])+post
        

    @abc.abstractmethod
    def is_valid(self):
        pass


class SpotipyModelConfig(SpotipyConfig):
    def __init__(self, backbone: Literal["resnet", "unet"]="unet", in_channels: int=1, out_channels: int=1, initial_fmaps: int=32,
                 n_convs_per_level: int=3, downsample_factor: int=2, kernel_size: int=3,
                 padding: Union[int, str]="same", levels: int=4, mode: Literal["direct", "fpn"]="direct", background_remover: bool=True,
                 batch_norm: bool=False, downsample_factors: Optional[Tuple[Tuple[int, int]]]=None, kernel_sizes: Optional[Tuple[Tuple[int, int]]]=None,
                 dropout: float=0., **kwargs):
        self.backbone = backbone
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.initial_fmaps = initial_fmaps
        self.n_convs_per_level = n_convs_per_level
        if downsample_factors is None:
            self.downsample_factors = tuple((downsample_factor, downsample_factor) for _ in range(levels))
        else:
            log.warning("Using downsample_factors argument. downsample_factor will be ignored.")
            self.downsample_factors = downsample_factors
        if kernel_sizes is None:
            self.kernel_sizes = tuple((kernel_size, kernel_size) for _ in range(n_convs_per_level))
        else:
            log.warning("Using kernel_sizes argument. kernel_size will be ignored.")
            self.kernel_sizes = kernel_sizes
        self.padding = padding
        self.levels = levels
        self.mode = mode
        self.background_remover = bool(background_remover)
        self.batch_norm = bool(batch_norm)
        self.dropout = dropout

        super().__init__()
    
    def is_valid(self):
        assert self.backbone in {"resnet", "unet"}, "backbone must be either 'resnet' or 'unet'"
        assert isinstance(self.in_channels, int) and self.in_channels > 0, "in_channels must be greater than 0"
        assert isinstance(self.out_channels, int) and self.out_channels > 0, "out_channels must be greater than 0"
        assert isinstance(self.initial_fmaps, int) and self.initial_fmaps > 0, "initial_fmaps must be greater than 0"
        assert isinstance(self.n_convs_per_level, int) and self.n_convs_per_level > 0, "n_convs_per_level must be greater than 0"
        assert all(isinstance(factor, tuple) and len(factor) == 2 for factor in self.downsample_factors), "downsample_factors must be a tuple of tuples of length 2"
        assert all(isinstance(f, int) and f > 0 for factor in self.downsample_factors for f in factor), "downsample_factors must be a tuple of tuples of integers"
        assert len(self.kernel_sizes) == self.n_convs_per_level, "kernel_sizes must have length equal to n_convs_per_level"
        assert all(isinstance(ksize, tuple) and len(ksize) == 2 for ksize in self.kernel_sizes), "kernel_sizes must be a tuple of tuples of length 2"
        assert all(isinstance(k, int) and k > 0 for ksize in self.kernel_sizes for k in ksize), "kernel_sizes must be a tuple of tuples of integers"
        assert isinstance(self.padding, int) or self.padding in {"same", "valid"}, "padding must be either 'same' or 'valid'"
        assert isinstance(self.padding, str) or self.padding >= 0, "padding must be greater than or equal to 0"
        assert self.levels > 0, "levels must be greater than 0"
        assert self.mode in {"direct", "fpn"}, "mode must be either 'direct' or 'fpn'"
        assert 0. <= self.dropout <= 1., "dropout must be between 0 and 1"


class SpotipyTrainingConfig(SpotipyConfig):
    def __init__(self, sigma: Number=1., crop_size: int=512, smart_crop: bool=False, loss_f: str="bce",
                 num_train_samples: Optional[int]=None,
                 pos_weight: Number=10., lr: float=3e-4, optimizer: str="adamw", batch_size: int=4,
                 num_epochs: int=200, **kwargs):
        self.sigma = sigma
        self.crop_size = crop_size
        self.smart_crop = bool(smart_crop)
        self.loss_f = loss_f
        self.pos_weight = pos_weight
        self.lr = lr
        self.optimizer = optimizer
        self.batch_size = batch_size
        self.num_epochs = num_epochs
        self.num_train_samples = num_train_samples
        super().__init__()

    
    def is_valid(self):
        assert isinstance(self.sigma, Number) and self.sigma >= 0, "sigma must be a number >= 0."
        assert isinstance(self.crop_size, int) and self.crop_size > 0, "crop_size must be an integer > 0."
        assert self.loss_f in {"bce", "mse", "smoothl1", "adawing"}, "loss_f must be either 'bce', 'mse', 'smoothl1', or 'adawing'"
        assert isinstance(self.pos_weight, Number) and self.pos_weight > 0, "pos_weight must be a number greater than 0."
        assert isinstance(self.lr, float) and self.lr > 0, "lr must be a floating point number greater than 0."
        assert self.optimizer in {"adamw"}, "optimizer must be 'adamw'"
        assert isinstance(self.batch_size, int) and self.batch_size > 0, "batch_size must be an integer greater than 0."
        assert isinstance(self.num_epochs, int) and self.num_epochs > 0, "num_epochs must be an integer greater than 0."
