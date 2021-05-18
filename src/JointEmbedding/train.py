import configparser  # implements a basic configuration language for Python programs
import os  # Provides a portable way of using operating system dependent functionality
import shutil
import sys  # System-specific parameters and functions
from collections import defaultdict  # dict subclass that calls a factory function to supply missing values
from copy import deepcopy  # creates a new object and recursively copies the original object elements
from urllib import parse  # standard interface to break Uniform Resource Locator (URL) in components

import baker  # Easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # The fundamental package for scientific computing with Python
import torch  # Tensor library like NumPy, with strong GPU support
from logzero import logger  # Robust and effective logging for Python

from utils.dataset import Dataset
from utils.generators import get_generator
from utils.nets import JointEmbeddingNet, compute_loss

# get config file path
joint_embedding_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(joint_embedding_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['jointEmbedding']['device']


@baker.command
def train_network(ds_path,  # path of the directory where to find the pre-processed dataset (containing .dat files)
                  run_id=None, #
                  training_run=0,  # training run identifier
                  batch_size=8192,  # how many samples per batch to load
                  epochs=10,  # How many epochs to train for
                  training_n_samples=-1,  # number of training samples to consider (used to access the right files)
                  validation_n_samples=-1,  # number of validation samples to consider (used to access the right files)
                  use_malicious_labels=1,  # Whether or not to use malware/benignware labels as a target
                  use_count_labels=1,  # Whether or not to use the counts as an additional target
                  feature_dimension=2381,  # The input dimension of the model
                  # if provided, seed random number generation with this value (defaults None, no seeding)
                  random_seed=None,
                  # How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
                  workers=None):
    """ Train a feed-forward neural network on EMBER 2.0 features, optionally with additional targets.
    SMART tags are based on (https://arxiv.org/abs/1905.06262)

    Args:
        ds_path: Path of the directory where to find the pre-processed dataset (containing .dat files)
        training_run: Training run identifier (default: 0) -> to plot base evaluation results with mean and confidence
                      we need at least 2 runs
        batch_size: How many samples per batch to load (default: 8192)
        epochs: How many epochs to train for; defaults to 10
        training_n_samples: Number of training samples to consider (used to access the right files)
        validation_n_samples: Number of validation samples to consider (used to access the right files)
        use_malicious_labels: Whether or not to use malware/benignware labels as a target; defaults to False
        use_count_labels: Whether or not to use the counts as an additional target; defaults to False
        feature_dimension: The input dimension of the model; defaults to 2381 (EMBER 2.0 feature size)
        random_seed: if provided, seed random number generation with this value (defaults None, no seeding)
        workers: How many worker processes should the dataloader use (default None, use multiprocessing.cpu_count())
    """
    if run_id == '0':
        run_id = None

    # start mlflow run
    with mlflow.start_run() as mlrun:

        # if workers has a value (it is not None) then convert it to int
        workers = workers if workers is None else int(workers)

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('...instantiating network for training run n. {}'.format(training_run))

        # create malware-NN model
        model = JointEmbeddingNet(use_malware=bool(use_malicious_labels),
                                  use_counts=bool(use_count_labels),
                                  n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                                  feature_dimension=feature_dimension,
                                  embedding_dimension=32)

        # use Adam optimizer on all the model parameters
        opt = torch.optim.Adam(model.parameters())

        # create generator (a.k.a. Dataloader)
        generator = get_generator(ds_root=ds_path,
                                  batch_size=batch_size,
                                  mode='train',
                                  num_workers=workers,
                                  n_samples=training_n_samples,
                                  use_malicious_labels=bool(use_malicious_labels),
                                  use_count_labels=bool(use_count_labels),
                                  use_tag_labels=True)

        # create validation generator (a.k.a. validation Dataloader)
        val_generator = get_generator(ds_root=ds_path,
                                      batch_size=batch_size,
                                      mode='validation',
                                      num_workers=workers,
                                      n_samples=validation_n_samples,
                                      use_malicious_labels=bool(use_malicious_labels),
                                      use_count_labels=bool(use_count_labels),
                                      use_tag_labels=True)

        # get number of steps per epoch (# of total batches) from generator
        steps_per_epoch = len(generator)
        # get number of validation steps per epoch (# of total validation batches) from validation generator
        val_steps_per_epoch = len(val_generator)

        if run_id is not None:
            previous_run = mlflow.tracking.MlflowClient().get_run(run_id)

            # get artifact path current submitted run
            artifact_src_path = parse.unquote(
                parse.urlparse(os.path.join(previous_run.info.artifact_uri, "model_checkpoints")).path)
            # get artifact path from submitted run
            artifact_dest_path = parse.unquote(
                parse.urlparse(os.path.join(mlrun.info.artifact_uri, "model_checkpoints")).path)

            # copy logged artifacts of the resumed run in the new one
            shutil.copytree(artifact_src_path, artifact_dest_path)

            print(previous_run.data.metrics)
            mlflow.log_metrics(previous_run.data.metrics)

        # get artifact path from current run
        artifact_path = parse.unquote(parse.urlparse(os.path.join(mlflow.get_artifact_uri(), "model_checkpoints")).path)

        # try loading the model from checkpoint (if it exists) and return epoch to start from
        start_epoch = model.load(artifact_path)

        # allocate model to selected device
        model.to(device)

        # loop for the selected number of epochs
        for epoch in range(start_epoch, epochs + 1):
            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)
            # set the model mode to 'train'
            model.train()

            # for all the training batches
            for i, (features, labels) in enumerate(generator):
                opt.zero_grad()  # clear old gradients from the last step

                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(features).to(device)

                # perform a forward pass through the network
                out = model(features)

                # compute loss given the predicted output from the model
                loss_dict = compute_loss(out, deepcopy(labels))  # copy the ground truth labels

                # extract total loss
                loss = loss_dict['total']

                # compute gradients
                loss.backward()

                # update model parameters
                opt.step()

                # for all the calculated losses in loss_dict
                for k in loss_dict.keys():
                    # if the loss is 'total' then append it to loss_histories['total'] after having detached it
                    # and passed it to the cpu
                    if k == 'total':
                        loss_histories[k].append(deepcopy(loss_dict[k].detach().cpu().item()))
                    # otherwise append the loss to loss_histories without having to detach it
                    else:
                        loss_histories[k].append(loss_dict[k])

                # create loss string with the current losses
                loss_str = " ".join([f"{key} loss:{value:7.3f}" for key, value in loss_dict.items()])
                loss_str += " | "
                loss_str += " ".join([f"{key} mean:{np.mean(value):7.3f}" for key, value in loss_histories.items()])
                # write on standard out the loss string + other information
                sys.stdout.write('\r Epoch: {}/{} {}/{} '.format(epoch, epochs, i + 1, steps_per_epoch) + loss_str)
                # flush standard output
                sys.stdout.flush()
                del features, labels  # to avoid weird references that lead to generator errors

            # log mean losses
            for key, value in loss_histories.items():
                mlflow.log_metric("train_loss_" + key, np.mean(value), step=epoch)

            # save model in checkpoint dir
            model.save(epoch)

            print()

            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)
            # set the model mode to 'eval'
            model.eval()

            # for all the validation batches
            for i, (features, labels) in enumerate(val_generator):
                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(features).to(device)

                with torch.no_grad():  # disable gradient calculation
                    # perform a forward pass through the network
                    out = model(features)

                # compute loss given the predicted output from the model
                loss_dict = compute_loss(out, deepcopy(labels))  # copy the ground truth labels

                # for all the calculated losses in loss_dict
                for k in loss_dict.keys():
                    # if the loss is 'total' then append it to loss_histories['total'] after having detached it
                    # and passed it to the cpu
                    if k == 'total':
                        loss_histories[k].append(deepcopy(loss_dict[k].detach().cpu().item()))
                    # otherwise append the loss to loss_histories without having to detach it
                    else:
                        loss_histories[k].append(loss_dict[k])

                # create loss string with the current losses
                loss_str = " ".join([f"{key} loss:{value:7.3f}" for key, value in loss_dict.items()])
                loss_str += " | "
                loss_str += " ".join([f"{key} mean:{np.mean(value):7.3f}" for key, value in loss_histories.items()])
                # write on standard out the loss string + other information
                sys.stdout.write('\r   Val: {}/{} {}/{} '.format(epoch, epochs, i + 1, val_steps_per_epoch) + loss_str)
                # flush standard output
                sys.stdout.flush()
                del features, labels  # to avoid weird references that lead to generator errors

            # log mean losses
            for key, value in loss_histories.items():
                mlflow.log_metric("valid_loss_" + key, np.mean(value), step=epoch)

            print()

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
