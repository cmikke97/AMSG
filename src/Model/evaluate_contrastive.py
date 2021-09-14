import configparser  # implements a basic configuration language for Python programs
import importlib  # provides the implementation of the import statement in Python source code
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
import time
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
import psutil
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python

from nets.generators.fresh_dataset import Dataset
from nets.generators.fresh_generators import get_generator
from nets.Contrastive_net import Net
from utils.ranking_metrics import (mean_reciprocal_rank, mean_average_precision,
                                   max_reciprocal_rank, min_reciprocal_rank,
                                   max_average_precision, min_average_precision)


np.set_printoptions(threshold=sys.maxsize)
np.set_printoptions(linewidth=sys.maxsize)

np.set_printoptions(threshold=sys.maxsize)
np.set_printoptions(linewidth=sys.maxsize)

# get config file path
model_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['general']['device']
N_SAMPLES = int(config['sorel20mDataset']['test_n_samples'])

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


def compute_ranking_scores(rank_per_query):
    # compute binarized (0/1) relevance scores
    rs = [np.asarray([i == rank['ground_truth_label'] for i in rank['rank_labels']], dtype=np.dtype(int))
          for rank in rank_per_query]

    # compute and log MRR and MAP scores
    ranking_scores = {'MRR': mean_reciprocal_rank(rs), 'MAP': mean_average_precision(rs)}

    max_rr, max_rr_idx = max_reciprocal_rank(rs)
    min_rr, min_rr_idx = min_reciprocal_rank(rs)
    max_ap, max_ap_idx = max_average_precision(rs)
    min_ap, min_ap_idx = min_average_precision(rs)

    # compute a bunch of indexes for interesting queries to save in csv files as examples
    queries_indexes = {
        'max_rr': {'value': max_rr, 'index': max_rr_idx},
        'min_rr': {'value': min_rr, 'index': min_rr_idx},
        'max_ap': {'value': max_ap, 'index': max_ap_idx},
        'min_ap': {'value': min_ap, 'index': min_ap_idx}
    }

    # get interesting queries
    ranks_to_save = {
        key: {
            'value': scores['value'],
            'rank': rank_per_query[scores['index']]
        }
        for key, scores in queries_indexes.items()
    }

    return ranking_scores, ranks_to_save


@baker.command
def evaluate_fresh(fresh_ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                   checkpoint_path,  # path to the model checkpoint to load
                   training_run=0,  # training run identifier
                   train_split_proportion=7,
                   valid_split_proportion=1,
                   test_split_proportion=2,
                   batch_size=250,  # how many samples per batch to load
                   rank_size=20,
                   knn_k_min=1,
                   knn_k_max=11,
                   # if provided, seed random number generation with this value (default: None, no seeding)
                   random_seed=None,
                   # how many worker (threads) the dataloader uses (default: 0 -> use multiprocessing.cpu_count())
                   workers=0):
    """ Evaluate the model on both the family prediction task and on the family ranking task.

    Args:
        fresh_ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        training_run: Training run identifier
        train_split_proportion:
        valid_split_proportion:
        test_split_proportion:
        batch_size: How many samples per batch to load
        rank_size:
        knn_k_min:
        knn_k_max:
        random_seed: If provided, seed random number generation with this value (default: None, no seeding)
        workers: How many worker (threads) the dataloader uses (default: 0 -> use multiprocessing.cpu_count())
    """

    # start mlflow run
    with mlflow.start_run() as mlrun:
        if train_split_proportion <= 0 or valid_split_proportion <= 0 or test_split_proportion <= 0:
            raise ValueError('train, valid and test split proportions must be positive integers.')

        if rank_size > batch_size:
            raise ValueError('rank size should be smaller or equal to the batch size.')

        dataset_split_proportions = [train_split_proportion, valid_split_proportion, test_split_proportion]

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('...instantiating siamese network for contrastive evaluation run n. {}'.format(training_run))

        # create fresh dataset generator
        train_generator, _, test_generator = get_generator(ds_root=fresh_ds_path,
                                                           splits=dataset_split_proportions,
                                                           batch_size=batch_size,
                                                           return_shas=True,
                                                           num_workers=workers,
                                                           shuffle=True)  # shuffle samples

        # get label to signature function from the test dataset (used to convert numerical labels to family names)
        label_to_sig = test_generator.dataset.label_to_sig

        # create contrastive (siamese) JointEmbeddingNet model
        model = Net(feature_dimension=2381,
                    embedding_dimension=32,
                    layer_sizes=run_additional_params['layer_sizes'],
                    dropout_p=run_additional_params['dropout_p'],
                    activation_function=run_additional_params['activation_function'],
                    normalization_function=run_additional_params['normalization_function'])

        model.load_state_dict(torch.load(checkpoint_path))

        # allocate model to selected device (CPU or GPU)
        model.to(device)

        logger.info('Evaluating contrastive learning model..')
        model.eval()

        # get number of steps per epoch (# of total batches) from test generator
        test_steps_per_epoch = len(test_generator)

        # get number of steps per epoch (# of total batches) from train generator
        train_steps_per_epoch = len(train_generator)

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            filename = os.path.join(tempdir, 'results.csv')

            ranks = []

            # set current epoch start time
            start_time = time.time()

            for i, (shas, features, labels) in enumerate(test_generator):
                # transfer features to selected device
                features = features.to(device)

                # perform a forward pass through the network and get embeddings
                pe_embeddings = model(features)

                top_shas = None
                top_labels = None
                top_distances = None

                for j, (anchor_shas, anchor_features, anchor_labels) in enumerate(train_generator):
                    # transfer anchor features to selected device
                    anchor_features = anchor_features.to(device)

                    # perform a forward pass through the network and get anchor embeddings
                    anchor_pe_embeddings = model(anchor_features)

                    distances = torch.cdist(pe_embeddings, anchor_pe_embeddings, p=2.0)

                    if top_distances is None:
                        top_distances = distances

                        indices = top_distances.argsort(dim=1)

                        top_shas = np.concatenate([np.expand_dims(
                            np.repeat(np.expand_dims(anchor_shas, axis=0), shas.shape[0], axis=0)[x, y], axis=0)
                            for x, row in enumerate(indices[:, :rank_size])
                            for y in row]).reshape(-1, rank_size)
                        top_labels = torch.cat([anchor_labels.repeat(labels.shape[0], 1)[x, y].unsqueeze(0)
                                                for x, row in enumerate(indices[:, :rank_size])
                                                for y in row]).view(-1, rank_size)
                        top_distances = torch.cat([top_distances[x, y].unsqueeze(0)
                                                   for x, row in enumerate(indices[:, :rank_size])
                                                   for y in row]).view(-1, rank_size)
                    else:
                        top_distances = torch.cat((top_distances, distances), dim=1)

                        top_shas = np.concatenate((top_shas, np.repeat(np.expand_dims(anchor_shas, axis=0),
                                                                       top_shas.shape[0], axis=0)), axis=1)
                        top_labels = torch.cat((top_labels, anchor_labels.repeat(top_labels.size()[0], 1)), dim=1)
                        top_distances = torch.cat((top_distances, distances), dim=1)

                        indices = top_distances.argsort(dim=1)

                        top_shas = np.concatenate([np.expand_dims(top_shas[x, y], axis=0)
                                                   for x, row in enumerate(indices[:, :rank_size])
                                                   for y in row]).reshape(-1, rank_size)
                        top_labels = torch.cat([top_labels[x, y].unsqueeze(0)
                                                for x, row in enumerate(indices[:, :rank_size])
                                                for y in row]).view(-1, rank_size)
                        top_distances = torch.cat([top_distances[x, y].unsqueeze(0)
                                                   for x, row in enumerate(indices[:, :rank_size])
                                                   for y in row]).view(-1, rank_size)

                for k, s in enumerate(shas):
                    ranks.append({
                        'query_sha': s,
                        'ground_truth_label': int(labels[k].item()),
                        'ground_truth_family': label_to_sig(int(labels[k].item())),
                        'rank_shas': top_shas[k].tolist(),
                        'rank_labels': [int(lab.item()) for lab in top_labels[k]],
                        'rank_families': [label_to_sig(int(lab.item())) for lab in top_labels[k]]
                    })

                # compute current epoch elapsed time (in seconds)
                elapsed_time = time.time() - start_time

                # write on standard out the elapsed time, predicted total epoch completion time, current mean speed
                # and main memory usage
                sys.stdout.write('\r Contrastive learning evaluation: {}/{} '.format(i + 1, test_steps_per_epoch)
                                 + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                 .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                         time.strftime("%H:%M:%S",  # predict total epoch completion time
                                                       time.gmtime(test_steps_per_epoch * elapsed_time / (i + 1))),
                                         (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                         psutil.virtual_memory().percent))  # get percentage of main memory used

                # flush standard output
                sys.stdout.flush()

            ranking_scores, ranks_to_save = compute_ranking_scores(ranks)

            mlflow.log_metric('MRR', float(ranking_scores['MRR']))
            mlflow.log_metric('MAP', float(ranking_scores['MAP']))

            # compute example ranks dataframes
            dataframes = {
                key: pd.DataFrame({"sha256": value['rank']['rank_shas'],
                                   "label": value['rank']['rank_labels'],
                                   "family": value['rank']['rank_families']})
                for key, value in ranks_to_save.items()
            }

            # compute example ranks metadata
            metadata = {
                key: pd.Series([
                    '{}: {}'.format(key, value['value']),
                    'Query sample sha256: {}'.format(value['rank']['query_sha']),
                    'Ground truth label: {}'.format(value['rank']['ground_truth_label']),
                    'Ground truth family: {}'.format(value['rank']['ground_truth_family'])
                ])
                for key, value in ranks_to_save.items()
            }

            logger.info('Saving results..')

            # for each example rank
            for df_key, df_val in dataframes.items():
                # retrieve metadata
                meta = metadata[df_key]

                # create file name
                df_filename = os.path.join(tempdir, '{}_example_rank.csv'.format(df_key))

                # open dataframe dest file and write both metadata and dataframe to it
                with open(df_filename, 'w') as df_f:
                    meta.to_csv(df_f, index=False)
                    df_val.to_csv(df_f)

            # log results file as artifact
            mlflow.log_artifact(filename, artifact_path="contrastive_learning_results")

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()