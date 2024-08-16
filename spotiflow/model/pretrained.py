from pathlib import Path
from dataclasses import dataclass

from ..utils import NotRegisteredError
from ..utils.get_file import get_file

@dataclass
class RegisteredModel:
    """
    Dataclass to store information about a registered model.

    url: the url of the zipped model folder
    md5_hash: the md5 hash of the zipped model folder
    """

    url: str
    md5_hash: str
    is_3d: bool

def list_registered():
    return list(_REGISTERED.keys())


def _cache_dir():
    return Path("~").expanduser() / ".spotiflow" / "models"


def get_pretrained_model_path(name: str):
    """
    Downloads and extracts the pretrained model with the given name.
    The model is downloaded to ~/.spotiflow and extracted to ~/.spotiflow/name.
    """
    if name not in _REGISTERED:
        raise NotRegisteredError(f"No pretrained model named {name} found. Available models: {','.join(sorted(list_registered()))}")
    model = _REGISTERED[name]
    path = Path(
        get_file(
            fname=f"{name}.zip",
            origin=model.url,
            file_hash=model.md5_hash,
            cache_dir=_cache_dir(),
            cache_subdir="",
            extract=True,
        )
    )
    return path.parent / name


_REGISTERED = {
    "hybiss": RegisteredModel(
        url="https://drive.switch.ch/index.php/s/O4hqFSSGX6veLwa/download",
        md5_hash="254afa97c137d0bd74fd9c1827f0e323",
        is_3d=False,
    ),
    "general": RegisteredModel(
        url="https://drive.switch.ch/index.php/s/6AoTEgpIAeQMRvX/download",
        md5_hash="9dd31a36b737204e91b040515e3d899e",
        is_3d=False,
    ),
    "synth_complex": RegisteredModel(
        url="https://drive.switch.ch/index.php/s/CiCjNJaJzpVVD2M/download",
        md5_hash="d692fa21da47e4a50b4c52f49442508b",
        is_3d=False,
    ),
    "synth_3d": RegisteredModel(
        url="https://drive.switch.ch/index.php/s/VhDqgDoHc11yP6v/download",
        md5_hash="a031f1284590886fbae37dc583c0270d",
        is_3d=True,
    ),
    "smfish_3d": RegisteredModel(
        url="https://drive.switch.ch/index.php/s/Vym7tqiORZOP5Zt/download",
        md5_hash="c5ab30ba3b9ccb07b4c34442d1b5b615",
        is_3d=True,
    )
}
