from collections import OrderedDict
from typing import List, Optional, Tuple, Union
import torch
import torch.nn as nn
import torch.nn.functional as F


from .backbones.unet import ConvBlock


class FeaturePyramidNetwork(nn.Module):
    """Feature Pyramid Network (Lin et al., CVPR '17) custom implementation allowing for different
    interpolation modes as well as extra control
    """

    def __init__(
        self,
        in_channels_list: List[int],
        out_channels: int,
        extra_blocks: Optional[nn.Module] = None,
        bias: bool = False,
        interpolation_mode: str = "bilinear",
        align_corners: bool = True,
        extra_modules: Optional[nn.ModuleList] = None,
    ) -> None:
        super().__init__()
        self.in_channels_list = in_channels_list
        self.out_channels = out_channels
        self.extra_blocks = extra_blocks
        self.premergers = nn.ModuleList(
            [
                nn.Conv2d(
                    in_channels=c,
                    out_channels=out_channels,
                    kernel_size=1,
                    padding=0,
                    bias=bias,
                )
                for c in in_channels_list
            ]
        )
        self.smoothers = nn.ModuleList(
            [
                nn.Conv2d(
                    in_channels=out_channels,
                    out_channels=out_channels,
                    kernel_size=3,
                    padding=1,
                    bias=bias,
                )
                for _ in in_channels_list
            ]
        )
        self.interpolation_mode = interpolation_mode
        self.align_corners = (
            align_corners
            if self.interpolation_mode in ["linear", "bilinear", "bicubic", "trilinear"]
            else None
        )
        self.extra_modules = extra_modules
        if self.extra_modules is not None:
            assert len(self.extra_modules) == len(
                self.in_channels_list
            ), "One extra module should be provided per feature map"

    def forward(self, feature_maps) -> OrderedDict:
        """Assumes highest resolution is first, lowest is last in the input object.
        Args:
            obj (OrderedDict): features maps computed from the backbone. Assumes highest resolution is first, lowest is last in the input object.

        Returns:
            OrderedDict: FPN-processed feature maps.
        """
        fpn_outputs = [None] * len(feature_maps)
        fpn_outputs[-1] = self.premergers[-1](feature_maps[-1])
        for idx in reversed(range(0, len(fpn_outputs) - 1)):  # lowest to highest
            # Upsample previous FPN output
            upsampled = F.interpolate(
                fpn_outputs[idx + 1],
                size=feature_maps[idx].shape[-2:],
                mode=self.interpolation_mode,
                align_corners=self.align_corners,
            )
            # Add a 1x1-conv processed version of the current feature map to the upsampled previous FPN level
            fpn_outputs[idx] = upsampled + self.premergers[idx](feature_maps[idx])

        # Run the final 3x3 convolution independently on the FPN outputs
        smoothed_fpn_output = [
            self.smoothers[i](val) for i, val in enumerate(fpn_outputs)
        ]
        return smoothed_fpn_output


class MultiHeadProcessor(nn.Module):
    def __init__(
        self,
        in_channels_list: List[int],
        out_channels: int,
        kernel_sizes: Tuple[Tuple[int, int]],
        initial_fmaps: int,
        fmap_inc_factor: float = 2,
        activation: nn.Module = nn.ReLU,
        batch_norm: bool = False,
        padding: Union[str, int] = "same",
        padding_mode: str = "zeros",
        dropout: int = 0,
    ):
        super().__init__()

        self.n_heads = len(in_channels_list)
        self.n_convs_per_head = len(kernel_sizes)
        self.activation = activation
        self.heads = nn.ModuleList()
        self.last_convs = (
            nn.ModuleList()
        )  # Need to be separated to avoid kaiming init on blocks with non-relu activations

        for h in range(self.n_heads):
            curr_head = []
            for n in range(self.n_convs_per_head):
                curr_head.append(
                    ConvBlock(
                        in_channels=in_channels_list[h]
                        if n == 0
                        else initial_fmaps * fmap_inc_factor**h,
                        out_channels=initial_fmaps * fmap_inc_factor**h,
                        kernel_size=kernel_sizes[n],
                        activation=self.activation,
                        padding=padding,
                        padding_mode=padding_mode,
                        batch_norm=batch_norm,
                        dropout=dropout,
                    )
                )

            self.heads.append(nn.Sequential(*curr_head))
            self.last_convs.append(
                ConvBlock(
                    in_channels=initial_fmaps * fmap_inc_factor**h,
                    out_channels=out_channels,
                    kernel_size=1,
                    batch_norm=batch_norm,
                    activation=nn.Identity,
                )
            )

        def init_kaiming(m):
            if self.activation is nn.ReLU:
                nonlinearity = "relu"
            elif self.activation is nn.LeakyReLU:
                nonlinearity = "leaky_relu"
            else:
                raise ValueError(
                    f"Kaiming init not applicable for activation {self.activation}."
                )
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, nonlinearity=nonlinearity)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

        if activation is nn.ReLU or activation is nn.LeakyReLU:
            self.heads.apply(init_kaiming)

    def forward(self, x: List[torch.Tensor]) -> List[torch.Tensor]:
        assert len(x) == self.n_heads, f"Expected {self.n_heads} inputs, got {len(x)}"
        out = []
        for _x, head, last in zip(x, self.heads, self.last_convs):
            y = head(_x)
            y = last(y)
            out.append(y)
        return out


class SimpleConv(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        n_layers: int = 3,
        activation: nn.Module = nn.ReLU,
        padding: Union[str, int] = "same",
        padding_mode: str = "zeros",
        dropout: int = 0,
    ):
        super().__init__()
        self.activation = activation
        layers = []
        for i in range(n_layers):
            last = i == n_layers - 1
            layers.append(
                ConvBlock(
                    in_channels,
                    out_channels if last else in_channels,
                    3,
                    padding=1,
                    bias=True,
                    activation=nn.Identity if last else activation,
                )
            )
        self.layers = nn.Sequential(*layers)

        def init_kaiming(m):
            if self.activation is nn.ReLU:
                nonlinearity = "relu"
            elif self.activation is nn.LeakyReLU:
                nonlinearity = "leaky_relu"
            else:
                raise ValueError(
                    f"Kaiming init not applicable for activation {self.activation}."
                )
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, nonlinearity=nonlinearity)
                nn.init.zeros_(m.bias)

        if activation is nn.ReLU or activation is nn.LeakyReLU:
            self.apply(init_kaiming)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.layers(x)
        return x
