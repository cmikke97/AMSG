import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import torch  # a neural networks library deeply integrated with autograd designed for maximum flexibility


def get_opt_state(opt,  # optimizer
                  path,  # path where to find the optimizer checkpoint
                  epoch):  # epoch to retrieve the optimizer state of
    """ Load optimizer state from path.

    Args:
        opt: Optimizer
        path: Path where to find the optimizer checkpoint
        epoch: Epoch to retrieve the optimizer state of
    Returns:
        Optimizer with loaded state (if found).
    """

    # compute optimizer checkpoint path
    opt_checkpoint_path = os.path.join(path, "opt_epoch_{}.pt".format(str(epoch)))

    # if the checkpoint exists and is a file then load it
    if os.path.exists(opt_checkpoint_path) and os.path.isfile(opt_checkpoint_path):
        opt.load_state_dict(torch.load(opt_checkpoint_path))

    # return optimizer
    return opt


def save_opt_state(opt,  # optimizer
                   epoch):  # epoch to save the optimizer state of
    """ Save optimizer state to temporary directory and then log it with mlflow.

    Args:
        opt: Optimizer
        epoch: Epoch to save the optimizer state of
    """

    # create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # compute optimizer checkpoint path
        opt_checkpoint_path = os.path.join(temp_dir, "opt_epoch_{}.pt".format(str(epoch)))

        # save optimizer state to checkpoint path
        torch.save(opt.state_dict(), opt_checkpoint_path)

        # log checkpoint file as artifact
        mlflow.log_artifact(opt_checkpoint_path, artifact_path="model_checkpoints")
