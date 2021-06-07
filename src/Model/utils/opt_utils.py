import os
import tempfile

import mlflow
import torch


def get_opt_state(opt,
                  path,
                  epoch):
    opt_checkpoint_path = os.path.join(path, "opt_epoch_{}.pt".format(str(epoch)))

    if os.path.exists(opt_checkpoint_path) and os.path.isfile(opt_checkpoint_path):
        opt.load_state_dict(torch.load(opt_checkpoint_path))

    return opt


def save_opt_state(opt,
                   epoch):
    # create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        opt_checkpoint_path = os.path.join(temp_dir, "opt_epoch_{}.pt".format(str(epoch)))

        torch.save(opt.state_dict(), opt_checkpoint_path)

        # log checkpoint file as artifact
        mlflow.log_artifact(opt_checkpoint_path, artifact_path="model_checkpoints")
