import configparser  # implements a basic configuration language for Python programs
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
import time  # provides various time-related functions
from collections import defaultdict  # dict subclass that calls a factory function to supply missing values
from copy import deepcopy  # creates a new object and recursively copies the original object elements
from urllib import parse

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
import psutil  # used for retrieving information on running processes and system utilization
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python

from nets.Family_classification_net import Net as Family_Net
from nets.generators.fresh_generators import get_generator

# get config file path
model_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['jointEmbedding']['device']

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
    'optimizer': config['jointEmbedding']['optimizer'],
    'lr': float(config['model_refinement']['lr']),
    'momentum': float(config['model_refinement']['momentum']),
    'weight_decay': float(config['model_refinement']['weight_decay']),
}


@baker.command
def refine_model(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                 checkpoint_path,  # path to the model checkpoint to load
                 refinement_run=0,  # refinement run identifier
                 epochs=10,
                 train_split_proportion=8,
                 valid_split_proportion=1,
                 test_split_proportion=1,
                 batch_size=1000,  # how many samples per batch to load
                 n_queries=100,  # number of queries to do in the family ranking task
                 # if provided, seed random number generation with this value (defaults None, no seeding)
                 random_seed=None,
                 # how many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())
                 workers=0):
    # start mlflow run
    with mlflow.start_run() as mlrun:
        if train_split_proportion <= 0 or valid_split_proportion <= 0 or test_split_proportion <= 0:
            raise ValueError('train, valid and test split proportions must be positive integers.')

        dataset_split_proportions = {
            'train': train_split_proportion,
            'valid': valid_split_proportion,
            'test': test_split_proportion
        }

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('...instantiating network for refinement run n. {}'.format(refinement_run))

        # create fresh dataset generator
        train_generator, valid_generator, test_generator = get_generator(ds_root=ds_path,
                                                                         splits=[8, 1, 1],
                                                                         batch_size=batch_size,
                                                                         return_shas=True,
                                                                         num_workers=workers,
                                                                         shuffle=True)  # shuffle samples

        # get label to signature function from the dataset (used to convert numerical labels to family names)
        label_to_sig = generator.dataset.label_to_sig

        n_families = generator.dataset.n_families
        n_samples = len(generator.dataset)

        valid_n_samples = n_samples * dataset_split_proportions['valid'] // sum(dataset_split_proportions.values())
        test_n_samples = n_samples * dataset_split_proportions['test'] // sum(dataset_split_proportions.values())
        train_n_samples = n_samples - valid_n_samples - test_n_samples

        # create JointEmbeddingNet model
        model = Family_Net(families=[label_to_sig(lab) for lab in range(n_families)],
                           feature_dimension=2381,
                           embedding_dimension=32,
                           layer_sizes=run_additional_params['layer_sizes'],
                           dropout_p=run_additional_params['dropout_p'],
                           activation_function=run_additional_params['activation_function'])

        # select optimizer is selected given the run additional parameters got from config file
        # if adam optimizer is selected
        if run_additional_params['optimizer'].lower() == 'adam':
            # use Adam optimizer on all the model parameters
            opt = torch.optim.Adam(model.parameters(),
                                   lr=run_additional_params['lr'],
                                   weight_decay=run_additional_params['weight_decay'])
        # else if sgd optimizer is selected
        elif run_additional_params['optimizer'].lower() == 'sgd':
            # use stochastic gradient descent on all the model parameters
            opt = torch.optim.SGD(model.parameters(),
                                  lr=run_additional_params['lr'],
                                  weight_decay=run_additional_params['weight_decay'],
                                  momentum=run_additional_params['momentum'])
        else:  # otherwise raise error
            raise ValueError('Unknown optimizer {}. Try "adam" or "sgd".'.format(run_additional_params['optimizer']))

        # load model parameters from checkpoint
        model.load_state_dict(torch.load(checkpoint_path), strict=False)

        # allocate model to selected device (CPU or GPU)
        model.to(device)

        # get number of steps per epoch (# of total batches) from generator
        steps_per_epoch = len(generator)

        valid_samples = get_n_samples_per_family(generator, model, valid_n_samples, n_families)
        test_samples = get_n_samples_per_family(generator, model, test_n_samples, n_families, avoid=valid_samples)

        logger.info('Refining model..')

        # loop for the selected number of epochs
        for epoch in range(1, epochs + 1):
            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)

            # set the model mode to 'train'
            model.train()

            # set current epoch start time
            start_time = time.time()

            # for all the training batches
            for i, (shas, features, labels) in enumerate(generator):
                opt.zero_grad()  # clear old gradients from the last step

                indices = [i for i, sha in enumerate(shas) if sha not in valid_samples['shas']
                           and sha not in test_samples['shas']]

                # select all train samples
                train_samples = {
                    'shas': [shas[i] for i in indices],
                    'features': features[indices],
                    'labels': labels[indices]
                }

                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(train_samples['features']).to(device)

                # perform a forward pass through the network
                out = model(features)

                # compute loss given the predicted output from the model
                loss_dict = model.compute_loss(out, deepcopy(train_samples['labels']))

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

                # compute current epoch elapsed time (in seconds)
                elapsed_time = time.time() - start_time

                # create loss string with the current loss
                loss_str = 'families prediction loss: {:7.3f}'.format(loss_dict['families'])

                # write on standard out the loss string + other information
                # (elapsed time, predicted total epoch completion time, current mean speed and main memory usage)
                sys.stdout.write('\r Refine epoch: {}/{} {}/{} '.format(epoch, epochs, i + 1, steps_per_epoch)
                                 + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                 .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                         time.strftime("%H:%M:%S",  # predict total epoch completion time
                                                       time.gmtime(steps_per_epoch * elapsed_time / (i + 1))),
                                         (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                         psutil.virtual_memory().percent)  # get percentage of main memory used
                                 + loss_str)  # append loss string

                # flush standard output
                sys.stdout.flush()
                del train_samples  # to avoid weird references that lead to generator errors

            # log mean losses as metrics
            for key, value in loss_histories.items():
                mlflow.log_metric("refine_train_loss_" + key, float(np.mean(value)), step=epoch)

            print()

            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)
            # set the model mode to 'eval'
            model.eval()

            # set current validation step start time
            start_time = time.time()

            # copy current features and allocate them on the selected device (CPU or GPU)
            features = deepcopy(valid_samples['features']).to(device)

            with torch.no_grad():  # disable gradient calculation
                # perform a forward pass through the network
                out = model(features)

            # compute loss given the predicted output from the model
            loss_dict = model.compute_loss(out, deepcopy(valid_samples['labels']))  # copy the ground truth labels

            # for all the calculated losses in loss_dict
            for k in loss_dict.keys():
                # if the loss is 'total' then append it to loss_histories['total'] after having detached it
                # and passed it to the cpu
                if k == 'total':
                    loss_histories[k].append(deepcopy(loss_dict[k].detach().cpu().item()))
                # otherwise append the loss to loss_histories without having to detach it
                else:
                    loss_histories[k].append(loss_dict[k])

            # compute current validation step elapsed time (in seconds)
            elapsed_time = time.time() - start_time

            # create loss string with the current loss
            loss_str = 'families prediction loss: {:7.3f}'.format(loss_dict['families'])

            # write on standard out the loss string + other information
            # (elapsed time, predicted total validation completion time, current mean speed and main memory usage)
            sys.stdout.write('\r Refine val: {}/{} {}/{} '.format(epoch, epochs, i + 1, 1)
                             + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                             .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                     time.strftime("%H:%M:%S",  # predict total validation completion time
                                                   time.gmtime(1 * elapsed_time / (i + 1))),
                                     (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                     psutil.virtual_memory().percent)  # get percentage of main memory used
                             + loss_str)  # append loss string

            # flush standard output
            sys.stdout.flush()

            # log mean losses as metrics
            for key, value in loss_histories.items():
                mlflow.log_metric("valid_loss_" + key, float(np.mean(value)), step=epoch)

            print()

            # save model state in current run checkpoint dir
            model.save(epoch)

        logger.info('...refinement done')

        logger.info('Evaluating refined model..')
        model.eval()

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            filename = os.path.join(tempdir, 'refined_results.csv')

            # create and open the results file in write mode
            with open(filename, 'w') as f:
                first_batch = True

                features = deepcopy(test_samples['features']).to(device)  # transfer features to selected device

                # perform a forward pass through the network and get predictions
                predictions = model(features)

                # normalize the results
                results = model.normalize_results(test_samples['labels'],
                                                  predictions)

                # store results into a pandas dataframe (indexed by the sha265 keys) and then save it as csv into
                # file f (inserting the header only if this is the first batch in the loop)
                pd.DataFrame(results, index=test_samples['shas']).to_csv(f, header=first_batch)

            # log results file as artifact
            mlflow.log_artifact(filename, artifact_path="refined_model_results")

        del test_samples
        logger.info('...evaluation done')

        checkpoint_dir = parse.unquote(parse.urlparse(os.path.join(mlrun.info.artifact_uri, "model_checkpoints")).path)
        checkpoint_path = os.path.join(checkpoint_dir, 'epoch_{}.pt'.format(epochs))


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
