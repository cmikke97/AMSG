import json
import os
import tempfile

import mlflow


def get_opt_state(opt,
                  path,
                  epoch):
    opt_checkpoint_path = os.path.join(path, "opt_epoch_{}.json".format(str(epoch)))

    if os.path.exists(opt_checkpoint_path) and os.path.isfile(opt_checkpoint_path):
        with open(opt_checkpoint_path, 'r') as opt_checkpoint:
            opt.load_state_dict(json.load(opt_checkpoint))

    return opt


def save_opt_state(opt,
                   epoch):
    # create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        opt_checkpoint_path = os.path.join(temp_dir, "opt_epoch_{}.json".format(str(epoch)))

        with open(opt_checkpoint_path, 'w') as opt_checkpoint:
            json.dump(opt.state_dict(), opt_checkpoint)

        # log checkpoint file as artifact
        mlflow.log_artifact(opt_checkpoint_path, artifact_path="model_checkpoints")
