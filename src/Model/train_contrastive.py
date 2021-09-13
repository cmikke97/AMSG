import configparser  # implements a basic configuration language for Python programs
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import time  # provides various time-related functions
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import psutil  # used for retrieving information on running processes and system utilization
import torch  # tensor library like NumPy, with strong GPU support
from torch.optim.lr_scheduler import MultiStepLR
from logzero import logger  # robust and effective logging for Python

from nets.generators.fresh_generators import get_generator
from nets.Contrastive_net import Net
from utils.contrastive_utils import batch_hard_triplet_loss, batch_all_triplet_loss

# get config file path
model_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['general']['device']

try:
    # try getting layer sizes from config file
    layer_sizes = json.loads(config['jointEmbedding']['layer_sizes'])
except json.JSONDecodeError:
    # if the option is not present in the config file set layer sizes to None
    layer_sizes = None

# instantiate run additional parameters dict setting values got from config file
run_additional_params = {
    'layer_sizes': layer_sizes,
    'dropout_p': float(config['jointEmbedding']['dropout_p']),
    'activation_function': config['jointEmbedding']['activation_function'],
    'normalization_function': config['jointEmbedding']['normalization_function'],
    'optimizer': config['contrastiveLearning']['optimizer'],
    'lr': float(config['contrastiveLearning']['lr']),
    'momentum': float(config['contrastiveLearning']['momentum']),
    'weight_decay': float(config['contrastiveLearning']['weight_decay']),
    'hard': int(config['contrastiveLearning']['hard']),
    'margin': float(config['contrastiveLearning']['margin']),
    'squared': int(config['contrastiveLearning']['squared'])
}


@baker.command
def train_network(fresh_ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                  checkpoint_path='None',  # path to the model checkpoint to load
                  training_run=0,  # training run identifier
                  epochs=25,
                  train_split_proportion=7,
                  valid_split_proportion=1,
                  test_split_proportion=2,
                  batch_size=250,  # how many samples per batch to load
                  # if provided, seed random number generation with this value (defaults None, no seeding)
                  random_seed=None,
                  # how many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())
                  workers=0):
    # start mlflow run
    with mlflow.start_run() as mlrun:
        if train_split_proportion <= 0 or valid_split_proportion <= 0 or test_split_proportion <= 0:
            raise ValueError('train, valid and test split proportions must be positive integers.')

        dataset_split_proportions = [train_split_proportion, valid_split_proportion, test_split_proportion]

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('...instantiating family classifier network for training run n. {}'.format(training_run))

        # create fresh dataset generator
        train_generator, valid_generator, _ = get_generator(ds_root=fresh_ds_path,
                                                            splits=dataset_split_proportions,
                                                            batch_size=batch_size,
                                                            return_shas=False,
                                                            num_workers=workers,
                                                            shuffle=True)  # shuffle samples

        # create JointEmbeddingNet model
        model = Net(feature_dimension=2381,
                    embedding_dimension=32,
                    layer_sizes=run_additional_params['layer_sizes'],
                    dropout_p=run_additional_params['dropout_p'],
                    activation_function=run_additional_params['activation_function'],
                    normalization_function=run_additional_params['normalization_function'])

        if checkpoint_path != 'None':
            # load model parameters from checkpoint
            model.load_state_dict(torch.load(checkpoint_path), strict=False)
            parameters_to_optimize = [
                {'params': model.pe_embedding.parameters(), 'lr': run_additional_params['lr']},
                {'params': model.model_base.parameters(), 'lr': run_additional_params['lr'] / 10}
            ]
        else:
            parameters_to_optimize = model.parameters()

        # select optimizer is selected given the run additional parameters got from config file
        # if adam optimizer is selected
        if run_additional_params['optimizer'].lower() == 'adam':
            # use Adam optimizer on all the model parameters
            opt = torch.optim.Adam(parameters_to_optimize,
                                   lr=run_additional_params['lr'],
                                   weight_decay=run_additional_params['weight_decay'])
        # else if sgd optimizer is selected
        elif run_additional_params['optimizer'].lower() == 'sgd':
            # use stochastic gradient descent on all the model parameters
            opt = torch.optim.SGD(parameters_to_optimize,
                                  lr=run_additional_params['lr'],
                                  weight_decay=run_additional_params['weight_decay'],
                                  momentum=run_additional_params['momentum'])
        else:  # otherwise raise error
            raise ValueError('Unknown optimizer {}. Try "adam" or "sgd".'.format(run_additional_params['optimizer']))

        scheduler = MultiStepLR(opt, milestones=[(3 * epochs) // 4], gamma=0.1)

        # allocate model to selected device (CPU or GPU)
        model.to(device)

        # get number of steps per epoch (# of total batches) from generator
        steps_per_epoch = len(train_generator)
        # get number of validation steps per epoch (# of total validation batches) from validation generator
        val_steps_per_epoch = len(valid_generator)

        logger.info('Training contrastive learning model..')

        # loop for the selected number of epochs
        for epoch in range(1, epochs + 1):
            loss_history = []

            # set the model mode to 'train'
            model.train()

            # set current epoch start time
            start_time = time.time()

            # for all the training batches
            for i, (features, labels) in enumerate(train_generator):
                opt.zero_grad()  # clear old gradients from the last step

                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(features).to(device)
                labels = deepcopy(labels.long()).to(device)

                # perform a forward pass through the network to get the embedding
                pe_embedding = model(features)

                # compute triplet loss given the output embedding
                if bool(run_additional_params['hard']):
                    loss = batch_hard_triplet_loss(labels,
                                                   pe_embedding,
                                                   margin=run_additional_params['margin'],
                                                   squared=bool(run_additional_params['squared']))
                else:
                    loss = batch_all_triplet_loss(labels,
                                                  pe_embedding,
                                                  margin=run_additional_params['margin'],
                                                  squared=bool(run_additional_params['squared']))

                # compute gradients
                loss.backward()

                # update model parameters
                opt.step()

                # append the loss to loss_histories
                loss_history.append(deepcopy(loss.detach().cpu().item()))

                # compute current epoch elapsed time (in seconds)
                elapsed_time = time.time() - start_time

                # create loss string with the current loss
                loss_str = 'Family prediction loss: {:7.3f}'.format(loss.detach().cpu().item())
                loss_str += ' | mean loss: {:7.3f}'.format(np.mean(loss_history))

                # write on standard out the loss string + other information
                # (elapsed time, predicted total epoch completion time, current mean speed and main memory usage)
                sys.stdout.write('\r Family classifier train epoch: {}/{} {}/{} '
                                 .format(epoch, epochs, i + 1, steps_per_epoch)
                                 + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                 .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                         time.strftime("%H:%M:%S",  # predict total epoch completion time
                                                       time.gmtime(steps_per_epoch * elapsed_time / (i + 1))),
                                         (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                         psutil.virtual_memory().percent)  # get percentage of main memory used
                                 + loss_str)  # append loss string

                # flush standard output
                sys.stdout.flush()
                del features, labels  # to avoid weird references that lead to generator errors

            scheduler.step()

            # log mean loss as metrics
            mlflow.log_metric("train_loss", float(np.mean(loss_history)), step=epoch)

            print()

            loss_history = []

            # set the model mode to 'eval'
            model.eval()

            # set current validation step start time
            start_time = time.time()

            # for all the validation batches
            for i, (features, labels) in enumerate(valid_generator):
                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(features).to(device)
                labels = deepcopy(labels.long()).to(device)

                with torch.no_grad():  # disable gradient calculation
                    # perform a forward pass through the network to get the embedding
                    pe_embedding = model(features)

                # compute triplet loss given the output embedding
                if bool(run_additional_params['hard']):
                    loss = batch_hard_triplet_loss(labels,
                                                   pe_embedding,
                                                   margin=run_additional_params['margin'],
                                                   squared=bool(run_additional_params['squared']))
                else:
                    loss = batch_all_triplet_loss(labels,
                                                  pe_embedding,
                                                  margin=run_additional_params['margin'],
                                                  squared=bool(run_additional_params['squared']))

                # append the loss to loss_histories
                loss_history.append(deepcopy(loss.detach().cpu().item()))

                # compute current validation step elapsed time (in seconds)
                elapsed_time = time.time() - start_time

                # create loss string with the current loss
                loss_str = 'Family prediction loss: {:7.3f}'.format(loss.detach().cpu().item())
                loss_str += ' | mean loss: {:7.3f}'.format(np.mean(loss_history))

                # write on standard out the loss string + other information
                # (elapsed time, predicted total validation completion time, current mean speed and main memory usage)
                sys.stdout.write('\r Family classifier val: {}/{} {}/{} '.format(epoch, epochs, i + 1,
                                                                                 val_steps_per_epoch)
                                 + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                 .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                         time.strftime("%H:%M:%S",  # predict total validation completion time
                                                       time.gmtime(val_steps_per_epoch * elapsed_time / (i + 1))),
                                         (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                         psutil.virtual_memory().percent)  # get percentage of main memory used
                                 + loss_str)  # append loss string

                # flush standard output
                sys.stdout.flush()
                del features, labels  # to avoid weird references that lead to generator errors

            # log mean loss as metrics
            mlflow.log_metric("valid_loss", float(np.mean(loss_history)), step=epoch)

            print()

            # save model state in current run checkpoint dir
            model.save(epoch)

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
