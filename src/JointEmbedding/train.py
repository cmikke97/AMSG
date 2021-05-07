import json  # JSON encoder and decoder
import os  # Provides a portable way of using operating system dependent functionality
import sys  # System-specific parameters and functions
# Imports defaultdict from collections (which implements specialized container datatypes providing alternatives
# to Python’s general purpose built-in containers)
import tempfile
from collections import defaultdict
# Used to construct a new compound object and then, recursively, insert copies into it of the objects found
# in the original
from copy import deepcopy
from urllib import parse

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np  # The fundamental package for scientific computing with Python
import torch  # Tensor library like NumPy, with strong GPU support
import torch.nn.functional as F  # pytorch neural network functional interface
from logzero import logger  # Robust and effective logging for Python
from waiting import wait

import config  # import config.py
from dataset import Dataset  # import Dataset.py
from generators import get_generator  # import get_generator function from Generators.py
from nets import JointEmbeddingNet  # import JointEmbeddingNet from Nets.py

import mlflow


def compute_loss(predictions,  # a dictionary of results from a PENetwork model
                 labels,  # a dictionary of labels
                 loss_wts=None):  # weights to assign to each head of the network (if it exists)
    """
    Compute losses for a malware feed-forward neural network (optionally with SMART tags
    and vendor detection count auxiliary losses).
    :param predictions: a dictionary of results from a PENetwork model
    :param labels: a dictionary of labels
    :param loss_wts: weights to assign to each head of the network (if it exists); defaults to
        values used in the ALOHA paper (1.0 for malware, 0.1 for count and each tag)
    """

    # if no loss_wts were provided set some default values
    if loss_wts is None:
        loss_wts = {'malware': 1.0,
                    'count': 0.1,
                    'tags': 1.0}

    loss_dict = {'total': 0.}  # initialize dictionary of losses

    if 'malware' in labels:  # if the malware head is enabled
        # extract ground truth malware label, convert it to float and allocate it into the selected device (CPU or GPU)
        malware_labels = labels['malware'].float().to(config.device)

        # get predicted malware label, reshape it to the same shape of malware_labels
        # then calculate binary cross entropy loss with respect to the ground truth malware labels
        malware_loss = F.binary_cross_entropy(predictions['malware'].reshape(malware_labels.shape),
                                              malware_labels)

        # get loss weight (or set to default if not provided)
        weight = loss_wts['malware'] if 'malware' in loss_wts else 1.0

        # copy calculated malware loss into the loss dictionary
        loss_dict['malware'] = deepcopy(malware_loss.item())

        # update total loss
        loss_dict['total'] += malware_loss * weight

    if 'count' in labels:  # if the count head is enabled
        # extract ground truth count, convert it to float and allocate it into the selected device (CPU or GPU)
        count_labels = labels['count'].float().to(config.device)

        # get predicted count, reshape it to the same shape of count_labels
        # then calculate poisson loss with respect to the ground truth count
        count_loss = torch.nn.PoissonNLLLoss()(predictions['count'].reshape(count_labels.shape),
                                               count_labels)

        # get loss weight (or set to default if not provided)
        weight = loss_wts['count'] if 'count' in loss_wts else 1.0

        # copy calculated count loss into the loss dictionary
        loss_dict['count'] = deepcopy(count_loss.item())

        # update total loss
        loss_dict['total'] += count_loss * weight

    if 'tags' in labels:  # if the tags (Joint Embedding) head is enabled
        # extract ground truth tags, convert them to float and allocate them into the selected device (CPU or GPU)
        tag_labels = labels['tags'].float().to(config.device)

        # get logit score from model prediction
        logit_score = predictions['logit_score']

        similarity_loss = F.binary_cross_entropy_with_logits(logit_score,
                                                             tag_labels,
                                                             reduction='none').sum(dim=1).mean(dim=0)

        # get loss weight (or set to default if not provided)
        weight = loss_wts['tags'] if 'tags' in loss_wts else 1.0

        # copy calculated tags loss into the loss dictionary
        loss_dict['jointEmbedding'] = deepcopy(similarity_loss.item())

        # update total loss
        loss_dict['total'] += similarity_loss * weight

    return loss_dict  # return the losses


@baker.command
def train_network(train_db_path=config.db_path,  # Path in which the meta.db is stored
                  training_run=0,  # training run identifier
                  epochs=10,  # How many epochs to train for
                  use_malicious_labels=False,  # Whether or not to use malware/benignware labels as a target
                  use_count_labels=False,  # Whether or not to use the counts as an additional target
                  feature_dimension=2381,  # The input dimension of the model
                  # if provided, seed random number generation with this value (defaults None, no seeding)
                  random_seed=None,
                  # How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
                  workers=None,
                  # remove_missing_features:
                  # Strategy for removing missing samples, with meta.db entries but no associated features,
                  # from the data.
                  # Must be one of: 'scan', 'none', or path to a missing keys file.
                  # Setting to 'scan' (default) will check all entries in the LMDB and remove any keys that are
                  # missing -- safe but slow.
                  # Setting to 'none' will not perform a check, but may lead to a run failure if any features
                  # are missing.
                  # Setting to a path will attempt to load a json-serialized list of SHA256 values from the specified
                  # file, indicating which keys are missing and should be removed from the dataloader.
                  remove_missing_features='scan'):
    """
    Train a feed-forward neural network on EMBER 2.0 features, optionally with additional targets as
    described in the ALOHA paper (https://arxiv.org/abs/1903.05700).  SMART tags based on
    (https://arxiv.org/abs/1905.06262)

    :param train_db_path: Path in which the meta.db is stored; defaults to the value specified in `config.py`
    :param training_run: Training run identifier (default: 0) -> to plot base evaluation results with mean
        and confidence we need at least 2 runs
    :param epochs: How many epochs to train for; defaults to 10
    :param use_malicious_labels: Whether or not to use malware/benignware labels as a target; defaults to False
    :param use_count_labels: Whether or not to use the counts as an additional target; defaults to False
    :param feature_dimension: The input dimension of the model; defaults to 2381 (EMBER 2.0 feature size)
    :param random_seed: if provided, seed random number generation with this value (defaults None, no seeding)
    :param workers: How many worker processes should the dataloader use (default None, use multiprocessing.cpu_count())
    :param remove_missing_features: Strategy for removing missing samples, with meta.db entries but no associated
        features, from the data (e.g. feature extraction failures).
        Must be one of: 'scan', 'none', or path to a missing keys file.
        Setting to 'scan' (default) will check all entries in the LMDB and remove any keys that are missing -- safe but
        slow.
        Setting to 'none' will not perform a check, but may lead to a run failure if any features are missing.
        Setting to a path will attempt to load a json-serialized list of SHA256 values from the specified file,
        indicating which keys are missing and should be removed from the dataloader.
    """
    # start mlflow run
    with mlflow.start_run() as mlrun:

        # if workers has a value (it is not None) then convert it to int
        workers = workers if workers is None else int(workers)

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        # log info
        logger.info('...instantiating network')

        # create malware-NN model
        model = JointEmbeddingNet(use_malware=use_malicious_labels,
                                  use_counts=use_count_labels,
                                  n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                                  feature_dimension=feature_dimension,
                                  embedding_dimension=32)

        # use Adam optimizer on all the model parameters
        opt = torch.optim.Adam(model.parameters())

        # create generator (a.k.a. Dataloader)
        generator = get_generator(path=train_db_path,
                                  mode='train',  # select train mode
                                  use_malicious_labels=use_malicious_labels,
                                  use_count_labels=use_count_labels,
                                  use_tag_labels=True,
                                  num_workers=workers,
                                  n_samples=config.training_n_samples_max,
                                  remove_missing_features=remove_missing_features)

        # create validation generator (a.k.a. validation Dataloader)
        val_generator = get_generator(path=train_db_path,
                                      mode='validation',  # select validation mode
                                      use_malicious_labels=use_malicious_labels,
                                      use_count_labels=use_count_labels,
                                      use_tag_labels=True,
                                      num_workers=workers,
                                      n_samples=config.validation_n_samples_max,
                                      remove_missing_features=remove_missing_features)

        # get number of steps per epoch (# of total batches) from generator
        steps_per_epoch = len(generator)
        # get number of validation steps per epoch (# of total validation batches) from validation generator
        val_steps_per_epoch = len(val_generator)

        # try loading the model from checkpoint (if it exists) and return epoch to start from
        start_epoch = model.load(training_run)

        # allocate model to selected device
        model.to(config.device)

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
                features = deepcopy(features).to(config.device)

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
                mlflow.log_metric("train_loss_" + key, np.mean(value))

            # save model in checkpoint dir
            model.save(training_run, epoch)

            print()

            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)
            # set the model mode to 'eval'
            model.eval()

            # for all the validation batches
            for i, (features, labels) in enumerate(val_generator):
                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(features).to(config.device)

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
                mlflow.log_metric("valid_loss_" + key, np.mean(value))

            print()

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
