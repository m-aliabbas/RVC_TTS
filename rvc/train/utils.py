import os
import glob
import torch
import numpy as np
from scipy.io.wavfile import read
from collections import OrderedDict
import matplotlib.pyplot as plt

MATPLOTLIB_FLAG = False


def replace_keys_in_dict(d, old_key_part, new_key_part):
    """
    Recursively replace parts of the keys in a dictionary.

    Args:
        d (dict or OrderedDict): The dictionary to update.
        old_key_part (str): The part of the key to replace.
        new_key_part (str): The new part of the key.
    """
    updated_dict = OrderedDict() if isinstance(d, OrderedDict) else {}
    for key, value in d.items():
        new_key = (
            key.replace(old_key_part, new_key_part) if isinstance(key, str) else key
        )
        updated_dict[new_key] = (
            replace_keys_in_dict(value, old_key_part, new_key_part)
            if isinstance(value, dict)
            else value
        )
    return updated_dict


def load_checkpoint(checkpoint_path, model, optimizer=None, load_opt=1):
    """
    Load a checkpoint into a model and optionally the optimizer.

    Args:
        checkpoint_path (str): Path to the checkpoint file.
        model (torch.nn.Module): The model to load the checkpoint into.
        optimizer (torch.optim.Optimizer, optional): The optimizer to load the state from. Defaults to None.
        load_opt (int, optional): Whether to load the optimizer state. Defaults to 1.
    """
    assert os.path.isfile(
        checkpoint_path
    ), f"Checkpoint file not found: {checkpoint_path}"

    checkpoint_dict = torch.load(checkpoint_path, map_location="cpu")
    checkpoint_dict = replace_keys_in_dict(
        replace_keys_in_dict(
            checkpoint_dict, ".weight_v", ".parametrizations.weight.original1"
        ),
        ".weight_g",
        ".parametrizations.weight.original0",
    )

    # Update model state_dict
    model_state_dict = (
        model.module.state_dict() if hasattr(model, "module") else model.state_dict()
    )
    new_state_dict = {
        k: checkpoint_dict["model"].get(k, v) for k, v in model_state_dict.items()
    }

    # Load state_dict into model
    if hasattr(model, "module"):
        model.module.load_state_dict(new_state_dict, strict=False)
    else:
        model.load_state_dict(new_state_dict, strict=False)

    if optimizer and load_opt == 1:
        optimizer.load_state_dict(checkpoint_dict.get("optimizer", {}))

    print(
        f"Loaded checkpoint '{checkpoint_path}' (epoch {checkpoint_dict['iteration']})"
    )
    return (
        model,
        optimizer,
        checkpoint_dict.get("learning_rate", 0),
        checkpoint_dict["iteration"],
    )


def save_checkpoint(model, optimizer, learning_rate, iteration, checkpoint_path):
    """
    Save the model and optimizer state to a checkpoint file.

    Args:
        model (torch.nn.Module): The model to save.
        optimizer (torch.optim.Optimizer): The optimizer to save the state of.
        learning_rate (float): The current learning rate.
        iteration (int): The current iteration.
        checkpoint_path (str): The path to save the checkpoint to.
    """
    state_dict = (
        model.module.state_dict() if hasattr(model, "module") else model.state_dict()
    )
    checkpoint_data = {
        "model": state_dict,
        "iteration": iteration,
        "optimizer": optimizer.state_dict(),
        "learning_rate": learning_rate,
    }
    torch.save(checkpoint_data, checkpoint_path)

    # Create a backwards-compatible checkpoint
    old_version_path = checkpoint_path.replace(".pth", "_old_version.pth")
    checkpoint_data = replace_keys_in_dict(
        replace_keys_in_dict(
            checkpoint_data, ".parametrizations.weight.original1", ".weight_v"
        ),
        ".parametrizations.weight.original0",
        ".weight_g",
    )
    torch.save(checkpoint_data, old_version_path)

    os.replace(old_version_path, checkpoint_path)
    print(f"Saved model '{checkpoint_path}' (epoch {iteration})")


def summarize(
    writer,
    global_step,
    scalars={},
    histograms={},
    images={},
    audios={},
    audio_sample_rate=22050,
):
    """
    Log various summaries to a TensorBoard writer.

    Args:
        writer (SummaryWriter): The TensorBoard writer.
        global_step (int): The current global step.
        scalars (dict, optional): Dictionary of scalar values to log.
        histograms (dict, optional): Dictionary of histogram values to log.
        images (dict, optional): Dictionary of image values to log.
        audios (dict, optional): Dictionary of audio values to log.
        audio_sample_rate (int, optional): Sampling rate of the audio data.
    """
    for k, v in scalars.items():
        writer.add_scalar(k, v, global_step)
    for k, v in histograms.items():
        writer.add_histogram(k, v, global_step)
    for k, v in images.items():
        writer.add_image(k, v, global_step, dataformats="HWC")
    for k, v in audios.items():
        writer.add_audio(k, v, global_step, audio_sample_rate)


def latest_checkpoint_path(dir_path, regex="G_*.pth"):
    """
    Get the latest checkpoint file in a directory.

    Args:
        dir_path (str): The directory to search for checkpoints.
        regex (str, optional): The regular expression to match checkpoint files.
    """
    checkpoints = sorted(
        glob.glob(os.path.join(dir_path, regex)),
        key=lambda f: int("".join(filter(str.isdigit, f))),
    )
    return checkpoints[-1] if checkpoints else None


def plot_spectrogram_to_numpy(spectrogram):
    """
    Convert a spectrogram to a NumPy array for visualization.

    Args:
        spectrogram (numpy.ndarray): The spectrogram to plot.

    Returns:
        numpy.ndarray: The rendered spectrogram as an image array.
    """
    global MATPLOTLIB_FLAG
    if not MATPLOTLIB_FLAG:
        plt.switch_backend("Agg")
        MATPLOTLIB_FLAG = True

    fig, ax = plt.subplots(figsize=(10, 2))
    im = ax.imshow(spectrogram, aspect="auto", origin="lower", interpolation="none")
    plt.colorbar(im, ax=ax)
    plt.xlabel("Frames")
    plt.ylabel("Channels")
    plt.tight_layout()

    # Render the figure
    fig.canvas.draw()
    
    # Get ARGB data from canvas
    data = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8)
    width, height = fig.canvas.get_width_height()

    # Reshape data to include 4 channels (ARGB)
    data = data.reshape((height, width, 4))

    # Convert ARGB to RGB by dropping the alpha channel
    data = data[..., 1:]  # Retain R, G, B channels only

    plt.close(fig)  # Close the figure to release memory
    return data



def load_wav_to_torch(full_path):
    """
    Load a WAV file into a PyTorch tensor.

    Args:
        full_path (str): The path to the WAV file.
    """
    sample_rate, data = read(full_path)
    return torch.FloatTensor(data.astype(np.float32)), sample_rate


def load_filepaths_and_text(filename, split="|"):
    """
    Load filepaths and associated text from a file.

    Args:
        filename (str): The path to the file.
        split (str, optional): The delimiter used to split the lines.
    """
    with open(filename, encoding="utf-8") as f:
        return [line.strip().split(split) for line in f]


class HParams:
    """
    A class for storing and accessing hyperparameters.
    """

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            self[k] = HParams(**v) if isinstance(v, dict) else v

    def keys(self):
        return self.__dict__.keys()

    def items(self):
        return self.__dict__.items()

    def values(self):
        return self.__dict__.values()

    def __len__(self):
        return len(self.__dict__)

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def __contains__(self, key):
        return key in self.__dict__

    def __repr__(self):
        return repr(self.__dict__)
